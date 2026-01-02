import os
import json
import time
import requests
import paramiko
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import List

# Carrega as variáveis do arquivo .env para o ambiente de execução.
load_dotenv()

# --- Modelos de Dados de Entrada (Request Body) ---
class BaserowDeployDetails(BaseModel):
    host: str = Field(..., description="O endereço IP público do servidor.", example="192.168.1.100")
    server_password: str = Field(..., description="A senha do utilizador root do servidor para a conexão SSH.")
    cloudflare_api_token: str = Field(..., description="Seu token de API da Cloudflare.")
    cloudflare_zone_id: str = Field(..., description="O ID da Zona (domínio) na Cloudflare.")
    baserow_domain: str = Field(..., description="O domínio que será usado para aceder ao Baserow.", example="baserow.meudominio.com")
    postgres_password: str = Field(..., description="A senha do banco de dados PostgreSQL que o Baserow usará.")
    portainer_url: str = Field(..., description="A URL completa para aceder à sua instância do Portainer.", example="https://portainer.meudominio.com")
    portainer_user: str = Field(..., description="O nome de utilizador do administrador do Portainer.", example="admin")
    portainer_password: str = Field(..., description="A senha do administrador do Portainer.")

# --- Instância do FastAPI ---
app = FastAPI(
    title="Baserow Deployer API",
    description="Uma API para limpar o banco de dados, configurar o DNS e implantar a stack do Baserow.",
    version="1.2.0" # Versão com desconexão forçada do DB
)

# --- Template da Stack Baserow ---
BASEROW_STACK_TEMPLATE = """
version: "3.7"
services:
  baserow:
    image: baserow/baserow:1.23.1
    hostname: "{{.Service.Name}}.{{.Task.Slot}}"
    volumes:
      - baserow_data:/baserow/data
    networks:
      - network_swarm_public
    environment:
      - BASEROW_PUBLIC_URL=https://{BASEROW_DOMAIN}
      - DATABASE_HOST=postgres
      - DATABASE_PORT=5432
      - DATABASE_USER=postgres
      - DATABASE_PASSWORD={POSTGRES_PASSWORD}
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
      labels:
        - "traefik.enable=true"
        - "traefik.http.routers.baserow.rule=Host(`{BASEROW_DOMAIN}`)"
        - "traefik.http.routers.baserow.entrypoints=websecure"
        - "traefik.http.routers.baserow.tls.certresolver=letsencryptresolver"
        - "traefik.http.routers.baserow.service=baserow"
        - "traefik.http.services.baserow.loadbalancer.server.port=80"
volumes:
  baserow_data: {}
networks:
  network_swarm_public:
    name: network_swarm_public
    external: true
"""

# --- Funções Auxiliares ---

def execute_ssh_command(ssh_client: paramiko.SSHClient, command: str, logs: List[str], ignore_errors: bool = False):
    logs.append(f"Executando comando SSH: {command}")
    stdin, stdout, stderr = ssh_client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()
    output = stdout.read().decode('utf-8').strip()
    error = stderr.read().decode('utf-8').strip()
    if output: logs.append(f"Saída: {output}")
    if error: logs.append(f"Erro: {error}")
    if not ignore_errors and exit_status != 0:
        raise Exception(f"Falha ao executar comando: '{command}'. Código de saída: {exit_status}")

def update_cloudflare_dns(details: BaserowDeployDetails, logs: List[str]):
    logs.append(f"Atualizando DNS para {details.baserow_domain} -> {details.host}")
    api_url = f"https://api.cloudflare.com/client/v4/zones/{details.cloudflare_zone_id}/dns_records"
    headers = {"Authorization": f"Bearer {details.cloudflare_api_token}", "Content-Type": "application/json"}
    response = requests.get(api_url, headers=headers, params={"name": details.baserow_domain})
    response.raise_for_status()
    records = response.json().get("result", [])
    payload = {"type": "A", "name": details.baserow_domain, "content": details.host, "ttl": 1, "proxied": False}
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
    time.sleep(15)
    logs.append("Propagação do DNS confirmada (simulado).")

# --- Endpoint da API ---
@app.post("/deploy-baserow", status_code=status.HTTP_200_OK)
def deploy_baserow_stack(details: BaserowDeployDetails):
    logs = []
    ssh_client = None
    try:
        # Passo 1: Limpar o banco de dados antigo via SSH
        logs.append("Passo 1: A conectar ao servidor via SSH para limpar o banco de dados...")
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname=details.host, port=22, username="root", password=details.server_password, timeout=15)
        
        find_postgres_cmd = "docker ps -q -f name=postgres_postgres"
        stdin, stdout, stderr = ssh_client.exec_command(find_postgres_cmd)
        postgres_container_id = stdout.read().decode('utf-8').strip()

        if not postgres_container_id:
            raise Exception("Não foi possível encontrar o contêiner do PostgreSQL em execução.")
        
        logs.append(f"Contêiner do PostgreSQL encontrado com ID: {postgres_container_id}")

        # CORREÇÃO: Força o encerramento de todas as conexões com o banco de dados 'baserow'
        terminate_sessions_cmd = f'docker exec {postgres_container_id} psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = \'baserow\';"'
        drop_db_cmd = f'docker exec {postgres_container_id} psql -U postgres -c "DROP DATABASE IF EXISTS baserow;"'
        create_db_cmd = f'docker exec {postgres_container_id} psql -U postgres -c "CREATE DATABASE baserow;"'

        execute_ssh_command(ssh_client, terminate_sessions_cmd, logs, ignore_errors=True)
        execute_ssh_command(ssh_client, drop_db_cmd, logs, ignore_errors=True)
        execute_ssh_command(ssh_client, create_db_cmd, logs)
        logs.append("Banco de dados 'baserow' recriado com sucesso.")
        ssh_client.close()

        # Passo 2: Configurar DNS na Cloudflare
        update_cloudflare_dns(details, logs)
        wait_for_dns_propagation(details.baserow_domain, details.host, logs)

        # Passo 3: Obter o token de acesso (JWT) do Portainer
        logs.append("Passo 3: A autenticar na API do Portainer...")
        auth_payload = {"Username": details.portainer_user, "Password": details.portainer_password}
        auth_url = f"{details.portainer_url}/api/auth"
        auth_response = requests.post(auth_url, json=auth_payload, verify=False)
        auth_response.raise_for_status()
        jwt_token = auth_response.json().get("jwt")
        logs.append("Autenticação bem-sucedida.")

        headers = {"Authorization": f"Bearer {jwt_token}"}

        # Passo 4: Encontrar o ID do endpoint e do Swarm
        logs.append("Passo 4: A procurar IDs do endpoint e do Swarm...")
        endpoints_url = f"{details.portainer_url}/api/endpoints"
        endpoints_response = requests.get(endpoints_url, headers=headers, verify=False)
        endpoints_response.raise_for_status()
        endpoints = endpoints_response.json()
        if not endpoints: raise Exception("Nenhum endpoint encontrado no Portainer.")
        endpoint_id = endpoints[0].get("Id")
        swarm_url = f"{details.portainer_url}/api/endpoints/{endpoint_id}/docker/swarm"
        swarm_response = requests.get(swarm_url, headers=headers, verify=False)
        swarm_response.raise_for_status()
        swarm_id = swarm_response.json().get("ID")
        logs.append(f"Endpoint ID: {endpoint_id}, Swarm ID: {swarm_id}")

        # Passo 5: Verificar se a stack "baserow" já existe
        logs.append("Passo 5: A verificar se a stack 'baserow' já existe...")
        stacks_url = f"{details.portainer_url}/api/stacks"
        stacks_response = requests.get(stacks_url, headers=headers, verify=False)
        stacks_response.raise_for_status()
        existing_stacks = stacks_response.json()
        baserow_stack = next((stack for stack in existing_stacks if stack.get("Name") == "baserow" and stack.get("EndpointId") == endpoint_id), None)

        stack_content = BASEROW_STACK_TEMPLATE.replace("{BASEROW_DOMAIN}", details.baserow_domain)
        stack_content = stack_content.replace("{POSTGRES_PASSWORD}", details.postgres_password)

        # Passo 6: Criar ou Atualizar a stack
        if baserow_stack:
            stack_id = baserow_stack.get("Id")
            logs.append(f"Stack 'baserow' encontrada com ID {stack_id}. A atualizar...")
            update_url = f"{details.portainer_url}/api/stacks/{stack_id}?endpointId={endpoint_id}"
            update_payload = {"StackFileContent": stack_content, "Prune": True}
            deploy_response = requests.put(update_url, headers=headers, json=update_payload, verify=False)
        else:
            logs.append("Stack 'baserow' não encontrada. A criar uma nova...")
            create_url = f"{details.portainer_url}/api/stacks/create/swarm/string?endpointId={endpoint_id}"
            create_payload = {"Name": "baserow", "SwarmID": swarm_id, "StackFileContent": stack_content}
            deploy_response = requests.post(create_url, headers=headers, json=create_payload, verify=False)

        deploy_response.raise_for_status()
        logs.append("Stack do Baserow implantada com sucesso através do Portainer.")
        return {"message": "Deu tudo certo"}

    except requests.exceptions.RequestException as e:
        error_message = f"Erro de comunicação com as APIs: {e}"
        if e.response is not None: error_message += f" | Resposta: {e.response.text}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
    except Exception as e:
        error_detail = {"detail": f"Ocorreu um erro inesperado: {str(e)}", "logs": logs}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)
    finally:
        if ssh_client and ssh_client.get_transport() and ssh_client.get_transport().is_active():
            ssh_client.close()