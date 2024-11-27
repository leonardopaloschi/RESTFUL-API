from fastapi import FastAPI, Depends, HTTPException, status, Request
from sqlalchemy import Column, String
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.future import Engine
from sqlalchemy import create_engine
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
from jose import jwt
import requests
import bcrypt
from fastapi.security import OAuth2PasswordBearer
# Carregar variáveis do arquivo .env
#load_dotenv(os.path.join("..", ".env"))
load_dotenv()

# Pegando as variáveis do arquivo .env
# DB_HOST = os.getenv("DB_HOST")
# DB_USER = os.getenv("DB_USER")
# DB_PASS = os.getenv("DB_PASS")
# DB_NAME = os.getenv("DB_NAME")
# Pegando as variáveis do arquivo .env
SECRET_KEY = os.getenv("SECRET_KEY")
user = os.getenv("USER")
password = os.getenv("PASSWORD")
host = os.getenv("HOST")
port = os.getenv("PORT")
database_name = os.getenv("DATABASE_NAME")


# Configuração do banco de dados
DATABASE_URL = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{database_name}"
print(f"DATABASE_URL: {DATABASE_URL}")
# Criação do engine para se conectar ao MySQL
engine: Engine = create_engine(DATABASE_URL, echo=True)


# Criação da base de metadados para SQLAlchemy
Base: DeclarativeMeta = declarative_base()

# Criando a sessão para o banco de dados
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Instância do FastAPI
app = FastAPI()

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Modelos do banco de dados
class Registros(Base):
    __tablename__ = "Registros"
    __table_args__ = {'schema': database_name}

    nome = Column(String(50), nullable=False)
    email = Column(String(50), nullable=False, primary_key=True)
    senha = Column(String(200), nullable=False)

class RegistroCreate(BaseModel):
    nome: str
    email: EmailStr
    senha: str

    class Config:
        orm_mode = True

class LoginData(BaseModel):
    email: EmailStr
    senha: str

# Função para criar um hash da senha
def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# Função para verificar a senha
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

# Função para criar um JWT Token baseado no nome e email
def create_access_token(nome: str, email: str, expires_delta: timedelta = None):
    to_encode = {"sub": email, "name": nome}
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Função para verificar o token JWT
def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token inválido")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token expirado")
# Dependência para obter a sessão do banco de dados
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Rotas da API

@app.post("/registrar", response_model=str)
def registrar_usuario(registro: RegistroCreate, db: Session = Depends(get_db)):
    # Verificar se o email já existe no banco de dados
    usuario_existente = db.query(Registros).filter(Registros.email == registro.email).first()
    if usuario_existente:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email já registrado")

    # Criar hash da senha
    hashed_password = get_password_hash(registro.senha)

    # Criar novo registro
    novo_registro = Registros(
        nome=registro.nome,
        email=registro.email,
        senha=hashed_password
    )

    # Adicionar e confirmar no banco de dados
    db.add(novo_registro)
    db.commit()
    db.refresh(novo_registro)

    # Gerar JWT Token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        nome=novo_registro.nome, email=novo_registro.email, expires_delta=access_token_expires
    )

    # Retornar JWT Token
    return access_token

@app.post("/login", response_model=str)
def login_usuario(login_data: LoginData, db: Session = Depends(get_db)):
    # Verificar se o email existe no banco de dados
    usuario = db.query(Registros).filter(Registros.email == login_data.email).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email inválido")

    # Verificar se a senha está correta
    if not verify_password(login_data.senha, usuario.senha):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha incorretos")

    # Gerar JWT Token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        nome=usuario.nome, email=usuario.email, expires_delta=access_token_expires
    )

    # Retornar JWT Token
    return access_token

@app.get("/consultar", response_model=dict)
def consultar_usuario(request: Request, token: str = Depends(oauth2_scheme)):
    user_data = verify_token(token)

    # Fazer requisição para a API externa
    response = requests.get("https://api.coincap.io/v2/assets/bitcoin")
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Erro ao consultar API externa")

    data = response.json()["data"]
    name = data["name"]
    symbol = data["symbol"]
    price_usd = float(data["priceUsd"])

    return {"message": f"A criptomoeda {name}({symbol}) atualmente vale U$ {price_usd:.2f}."}


# Função para criar as tabelas no schema existente
def create_tables():
    Base.metadata.create_all(bind=engine)

# Evento de inicialização para criar as tabelas automaticamente
@app.on_event("startup")
def on_startup():
    create_tables()
