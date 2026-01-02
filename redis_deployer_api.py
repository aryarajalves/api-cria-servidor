import os
import json
import time
import requests
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import List

# Carrega as variáveis do arquivo .env para o ambiente de execução.
load_dotenv()

# --- Modelos de Dados de Entrada (Request Body) ---
class RedisDeployDetails(BaseModel):
    portainer_url: str = Field(..., description="A URL completa para aceder à sua instância do Portainer.", example="https://portainer.meudominio.com")
    portainer_user: str = Field(..., description="O nome de utilizador do administrador do Portainer.", example="admin")
    portainer_password: str = Field(..., description="A senha do administrador do Portainer.")

# --- Instância do FastAPI ---
app = FastAPI(
    title="Redis Deployer API",
    description="Uma API para implantar uma stack Redis usando a API do Portainer.",
    version="2.0.0" # Versão com fluxo de API detalhado
)

# --- Template da Stack Redis ---
REDIS_STACK_TEMPLATE = """
version: "3.7"
services:
  redis:
    image: redis:7
    hostname: "{{.Service.Name}}.{{.Task.Slot}}"
    command: redis-server --appendonly yes --port 6379
    networks:
      - network_swarm_public
    volumes:
      - redis_data:/data
    deploy:
      mode: replicated
      replicas: 1
      placement:
        constraints:
          - node.role == manager
      resources:
        limits:
          cpus: "1"
          memory: 2048M
volumes:
  redis_data: {}
networks:
  network_swarm_public:
    external: true
    name: network_swarm_public
"""

# --- Endpoint da API ---
@app.post("/deploy-redis", status_code=status.HTTP_200_OK)
def deploy_redis_stack(details: RedisDeployDetails):
    """
    Autentica-se na API do Portainer e implanta ou atualiza a stack do Redis.
    """
    logs = []
    try:
        # Passo 1: Obter o token de acesso (JWT) do Portainer
        logs.append("Passo 1: A autenticar na API do Portainer...")
        auth_payload = {"Username": details.portainer_user, "Password": details.portainer_password}
        auth_url = f"{details.portainer_url}/api/auth"
        auth_response = requests.post(auth_url, json=auth_payload, verify=False)
        auth_response.raise_for_status()
        jwt_token = auth_response.json().get("jwt")
        logs.append("Autenticação bem-sucedida.")

        headers = {"Authorization": f"Bearer {jwt_token}"}

        # Passo 2: Encontrar o ID do endpoint
        logs.append("Passo 2: A procurar o ID do endpoint...")
        endpoints_url = f"{details.portainer_url}/api/endpoints"
        endpoints_response = requests.get(endpoints_url, headers=headers, verify=False)
        endpoints_response.raise_for_status()
        endpoints = endpoints_response.json()
        if not endpoints: raise Exception("Nenhum endpoint encontrado no Portainer.")
        endpoint_id = endpoints[0].get("Id")
        logs.append(f"Endpoint encontrado com ID: {endpoint_id}")

        # Passo 3: Obter o SwarmID
        logs.append("Passo 3: A procurar o ID do Swarm...")
        swarm_url = f"{details.portainer_url}/api/endpoints/{endpoint_id}/docker/swarm"
        swarm_response = requests.get(swarm_url, headers=headers, verify=False)
        swarm_response.raise_for_status()
        swarm_id = swarm_response.json().get("ID")
        logs.append(f"Swarm encontrado com ID: {swarm_id}")

        # Passo 4: Verificar se a stack "redis" já existe
        logs.append("Passo 4: A verificar se a stack 'redis' já existe...")
        stacks_url = f"{details.portainer_url}/api/stacks"
        stacks_response = requests.get(stacks_url, headers=headers, verify=False)
        stacks_response.raise_for_status()
        
        existing_stacks = stacks_response.json()
        redis_stack = next((stack for stack in existing_stacks if stack.get("Name") == "redis" and stack.get("EndpointId") == endpoint_id), None)

        # Passo 5: Criar ou Atualizar a stack
        if redis_stack:
            # Se existir, ATUALIZA a stack (PUT)
            stack_id = redis_stack.get("Id")
            logs.append(f"Stack 'redis' encontrada com ID {stack_id}. A atualizar...")
            
            update_url = f"{details.portainer_url}/api/stacks/{stack_id}?endpointId={endpoint_id}"
            update_payload = {
                "StackFileContent": REDIS_STACK_TEMPLATE,
                "Prune": True
            }
            deploy_response = requests.put(update_url, headers=headers, json=update_payload, verify=False)
        else:
            # Se não existir, CRIA a stack (POST)
            logs.append("Stack 'redis' não encontrada. A criar uma nova...")
            create_url = f"{details.portainer_url}/api/stacks/create/swarm/string?endpointId={endpoint_id}"
            create_payload = {
                "Name": "redis",
                "SwarmID": swarm_id,
                "StackFileContent": REDIS_STACK_TEMPLATE
            }
            deploy_response = requests.post(create_url, headers=headers, json=create_payload, verify=False)

        deploy_response.raise_for_status()

        logs.append("Stack do Redis implantada com sucesso através do Portainer.")
        
        return {"message": "Deu tudo certo"}

    except requests.exceptions.RequestException as e:
        error_message = f"Erro de comunicação com a API do Portainer: {e}"
        if e.response is not None:
            error_message += f" | Resposta: {e.response.text}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
    except Exception as e:
        error_detail = {"detail": f"Ocorreu um erro inesperado: {str(e)}", "logs": logs}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)