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
class RabbitMQDeployDetails(BaseModel):
    host: str = Field(..., description="O endereço IP público do servidor.", example="192.168.1.100")
    cloudflare_api_token: str = Field(..., description="Seu token de API da Cloudflare.")
    cloudflare_zone_id: str = Field(..., description="O ID da Zona (domínio) na Cloudflare.")
    rabbitmq_domain: str = Field(..., description="O domínio que será usado para aceder ao RabbitMQ.", example="rabbitmq.meudominio.com")
    rabbitmq_user: str = Field(..., description="O nome de utilizador para o RabbitMQ.")
    rabbitmq_password: str = Field(..., description="A senha para o utilizador do RabbitMQ.")
    portainer_url: str = Field(..., description="A URL completa para aceder à sua instância do Portainer.", example="https://portainer.meudominio.com")
    portainer_user: str = Field(..., description="O nome de utilizador do administrador do Portainer.", example="admin")
    portainer_password: str = Field(..., description="A senha do administrador do Portainer.")

# --- Instância do FastAPI ---
app = FastAPI(
    title="RabbitMQ Deployer API",
    description="Uma API para configurar o DNS e implantar a stack do RabbitMQ usando o Portainer.",
    version="1.0.0"
)

# --- Template da Stack RabbitMQ ---
RABBITMQ_STACK_TEMPLATE = """
version: "3.7"
services:
  rabbitmq:
    image: rabbitmq:3.11-management
    hostname: "{{.Service.Name}}.{{.Task.Slot}}"
    networks:
      - network_swarm_public
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq/
    environment:
      - RABBITMQ_ERLANG_COOKIE=6e766073c9c442feb7a4c66a562160fc
      - RABBITMQ_DEFAULT_VHOST=default
      - RABBITMQ_DEFAULT_USER={RABBITMQ_USER}
      - RABBITMQ_DEFAULT_PASS={RABBITMQ_PASSWORD}
    deploy:
      mode: replicated
      replicas: 1
      placement:
        constraints:
          - node.role == manager
      resources:
        limits:
          cpus: "1"
          memory: 1024M
      labels:
        - "traefik.enable=true"
        - "traefik.http.routers.rabbitmq.rule=Host(`{RABBITMQ_DOMAIN}`)"
        - "traefik.http.routers.rabbitmq.entrypoints=websecure"
        - "traefik.http.routers.rabbitmq.tls.certresolver=letsencryptresolver"
        - "traefik.http.routers.rabbitmq.service=rabbitmq"
        - "traefik.http.services.rabbitmq.loadbalancer.server.port=15672"
volumes:
  rabbitmq_data: {}
networks:
  network_swarm_public:
    name: network_swarm_public
    external: true
"""

# --- Funções Auxiliares ---

def update_cloudflare_dns(details: RabbitMQDeployDetails, logs: List[str]):
    logs.append(f"Atualizando DNS para {details.rabbitmq_domain} -> {details.host}")
    api_url = f"https://api.cloudflare.com/client/v4/zones/{details.cloudflare_zone_id}/dns_records"
    headers = {"Authorization": f"Bearer {details.cloudflare_api_token}", "Content-Type": "application/json"}
    response = requests.get(api_url, headers=headers, params={"name": details.rabbitmq_domain})
    response.raise_for_status()
    records = response.json().get("result", [])
    payload = {"type": "A", "name": details.rabbitmq_domain, "content": details.host, "ttl": 1, "proxied": False}
    if records:
        record_id = records[0]["id"]
        logs.append(f"Registro DNS encontrado com ID {record_id}. Atualizando...")
        response = requests.put(f"{api_url}/{record_id}", headers=headers, json=payload)
    else:
        logs.append("Nenhum registro DNS encontrado. Criando um novo...")
        response = requests.post(api_url, headers=headers, json=payload)
    response.raise_for_status()
    logs.append("Registro DNS na Cloudflare atualizado com sucesso.")

def wait_for_dns_propagation(domain: str, target_ip: str, logs: List[str]):
    logs.append(f"Aguardando propagação do DNS para {domain}...")
    # Simulação da espera
    time.sleep(15) 
    logs.append("Propagação do DNS confirmada (simulado).")


# --- Endpoint da API ---
@app.post("/deploy-rabbitmq", status_code=status.HTTP_200_OK)
def deploy_rabbitmq_stack(details: RabbitMQDeployDetails):
    """
    Configura o DNS, autentica-se no Portainer e implanta ou atualiza a stack do RabbitMQ.
    """
    logs = []
    try:
        # Passo 1: Configurar DNS na Cloudflare
        update_cloudflare_dns(details, logs)
        wait_for_dns_propagation(details.rabbitmq_domain, details.host, logs)

        # Passo 2: Obter o token de acesso (JWT) do Portainer
        logs.append("Passo 2: A autenticar na API do Portainer...")
        auth_payload = {"Username": details.portainer_user, "Password": details.portainer_password}
        auth_url = f"{details.portainer_url}/api/auth"
        auth_response = requests.post(auth_url, json=auth_payload, verify=False)
        auth_response.raise_for_status()
        jwt_token = auth_response.json().get("jwt")
        logs.append("Autenticação bem-sucedida.")

        headers = {"Authorization": f"Bearer {jwt_token}"}

        # Passo 3: Encontrar o ID do endpoint e do Swarm
        logs.append("Passo 3: A procurar IDs do endpoint e do Swarm...")
        endpoints_url = f"{details.portainer_url}/api/endpoints"
        endpoints_response = requests.get(endpoints_url, headers=headers, verify=False)
        endpoints_response.raise_for_status()
        endpoints = endpoints_response.json()
        if not endpoints: raise Exception("Nenhum endpoint encontrado no Portainer.")
        endpoint_id = endpoints[0].get("Id")
        logs.append(f"Endpoint ID: {endpoint_id}")

        swarm_url = f"{details.portainer_url}/api/endpoints/{endpoint_id}/docker/swarm"
        swarm_response = requests.get(swarm_url, headers=headers, verify=False)
        swarm_response.raise_for_status()
        swarm_id = swarm_response.json().get("ID")
        logs.append(f"Swarm ID específico encontrado: {swarm_id}")

        # Passo 4: Verificar se a stack "rabbitmq" já existe
        logs.append("Passo 4: A verificar se a stack 'rabbitmq' já existe...")
        stacks_url = f"{details.portainer_url}/api/stacks"
        stacks_response = requests.get(stacks_url, headers=headers, verify=False)
        stacks_response.raise_for_status()
        
        existing_stacks = stacks_response.json()
        rabbitmq_stack = next((stack for stack in existing_stacks if stack.get("Name") == "rabbitmq" and stack.get("EndpointId") == endpoint_id), None)

        # Prepara o conteúdo da stack, substituindo as variáveis
        stack_content = RABBITMQ_STACK_TEMPLATE.replace("{RABBITMQ_DOMAIN}", details.rabbitmq_domain)
        stack_content = stack_content.replace("{RABBITMQ_USER}", details.rabbitmq_user)
        stack_content = stack_content.replace("{RABBITMQ_PASSWORD}", details.rabbitmq_password)

        # Passo 5: Criar ou Atualizar a stack
        if rabbitmq_stack:
            stack_id = rabbitmq_stack.get("Id")
            logs.append(f"Stack 'rabbitmq' encontrada com ID {stack_id}. A atualizar...")
            update_url = f"{details.portainer_url}/api/stacks/{stack_id}?endpointId={endpoint_id}"
            update_payload = {"StackFileContent": stack_content, "Prune": True}
            deploy_response = requests.put(update_url, headers=headers, json=update_payload, verify=False)
        else:
            logs.append("Stack 'rabbitmq' não encontrada. A criar uma nova...")
            create_url = f"{details.portainer_url}/api/stacks/create/swarm/string?endpointId={endpoint_id}"
            create_payload = {"Name": "rabbitmq", "SwarmID": swarm_id, "StackFileContent": stack_content}
            deploy_response = requests.post(create_url, headers=headers, json=create_payload, verify=False)

        deploy_response.raise_for_status()

        logs.append("Stack do RabbitMQ implantada com sucesso através do Portainer.")
        
        return {"message": "Deu tudo certo"}

    except requests.exceptions.RequestException as e:
        error_message = f"Erro de comunicação com as APIs: {e}"
        if e.response is not None:
            error_message += f" | Resposta: {e.response.text}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
    except Exception as e:
        error_detail = {"detail": f"Ocorreu um erro inesperado: {str(e)}", "logs": logs}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)