import os
import requests
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any

# Carrega as variáveis do arquivo .env para o ambiente de execução.
load_dotenv()

# --- Configuração ---
N8N_URL = os.getenv("N8N_URL")
N8N_API_KEY = os.getenv("N8N_API_KEY")

if not N8N_URL or not N8N_API_KEY:
    raise ValueError(
        "As variáveis de ambiente N8N_URL e N8N_API_KEY devem ser definidas no arquivo .env"
    )

# --- Modelos de Dados para cada Credencial ---
# Usamos 'Optional' para que você possa enviar apenas as credenciais que deseja criar.

# ATUALIZAÇÃO: Modelo do Baserow modificado para usar host, username e password.
class BaserowCredentials(BaseModel):
    name: str = "Baserow Account"
    host: str
    username: str
    password: str

class TelegramCredentials(BaseModel):
    name: str = "Telegram Account"
    accessToken: str

# O modelo da OpenAI já estava correto, pedindo a apiKey.
class OpenAiCredentials(BaseModel):
    name: str = "OpenAI Account"
    apiKey: str

class PostgresCredentials(BaseModel):
    name: str = "Postgres Account"
    host: str
    database: str
    user: str
    password: str
    port: int = 5432
    ssl: bool = False

class RabbitMqCredentials(BaseModel):
    name: str = "RabbitMQ Account"
    host: str
    user: str
    password: str
    port: int = 5672

class RedisCredentials(BaseModel):
    name: str = "Redis Account"
    host: str
    port: int = 6379
    user: Optional[str] = None
    password: Optional[str] = None

# --- Modelo Principal da Requisição ---
class AllCredentialsRequest(BaseModel):
    baserow: Optional[BaserowCredentials] = None
    telegram: Optional[TelegramCredentials] = None
    openai: Optional[OpenAiCredentials] = None
    postgres: Optional[PostgresCredentials] = None
    rabbitmq: Optional[RabbitMqCredentials] = None
    redis: Optional[RedisCredentials] = None

# --- Instância do FastAPI ---
app = FastAPI(
    title="n8n Credentials Creator API",
    description="Uma API para criar um conjunto de credenciais no n8n de forma automática.",
    version="1.1.0" # Versão atualizada
)

# --- Função Auxiliar para Criar Credencial ---
def create_credential_in_n8n(name: str, cred_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Constrói o payload e envia a requisição para a API do n8n para criar uma credencial.
    """
    n8n_api_endpoint = f"{N8N_URL}/api/v1/credentials"
    headers = {
        "Accept": "application/json",
        "X-N8N-API-KEY": N8N_API_KEY
    }
    
    payload = {
        "name": name,
        "type": cred_type,
        "data": data
    }
    
    try:
        response = requests.post(n8n_api_endpoint, headers=headers, json=payload)
        response.raise_for_status()
        created_data = response.json()
        return {"status": "success", "id": created_data.get('id'), "name": name}
    except requests.exceptions.HTTPError as http_err:
        return {"status": "error", "name": name, "detail": http_err.response.text}
    except requests.exceptions.RequestException as req_err:
        return {"status": "error", "name": name, "detail": str(req_err)}

# --- Endpoint Principal ---
@app.post("/create-all-credentials", status_code=status.HTTP_201_CREATED)
def create_all_credentials(request_data: AllCredentialsRequest):
    """
    Recebe os dados de várias credenciais e tenta criar cada uma delas no n8n.
    """
    results = []
    
    # Mapeamento dos tipos de credenciais para os nomes na API do n8n
    CREDENTIAL_TYPE_MAP = {
        "baserow": "n8n-nodes-base.baserowApi",
        "telegram": "n8n-nodes-base.telegramApi",
        "openai": "n8n-nodes-base.openAiApi",
        "postgres": "n8n-nodes-base.postgres",
        "rabbitmq": "n8n-nodes-base.rabbitmq",
        "redis": "n8n-nodes-base.redis"
    }

    credentials_to_create = request_data.model_dump(exclude_none=True)

    if not credentials_to_create:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pelo menos uma credencial deve ser fornecida no corpo da requisição."
        )

    for key, cred_data in credentials_to_create.items():
        cred_name = cred_data.pop("name")
        cred_type = CREDENTIAL_TYPE_MAP.get(key)
        
        if cred_type:
            result = create_credential_in_n8n(cred_name, cred_type, cred_data)
            results.append(result)

    return {"message": "Processo de criação de credenciais finalizado.", "results": results}
