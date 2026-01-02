import os
import json
import paramiko
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import List

# Carrega as variáveis do arquivo .env para o ambiente de execução.
load_dotenv()

# --- Modelo de Dados de Entrada (Request Body) ---
class TraefikDeployDetails(BaseModel):
    host: str = Field(..., description="O endereço IP ou hostname do servidor.", example="192.168.1.100")
    password: str = Field(..., description="A senha do usuário root para a conexão SSH.")
    letsencrypt_email: str = Field(..., description="O e-mail para o resolvedor de certificados Let's Encrypt.", example="seuemail@dominio.com")

# --- Instância do FastAPI ---
app = FastAPI(
    title="Traefik Deployer API",
    description="Uma API para implantar uma stack Traefik em um servidor com Docker Swarm.",
    version="1.0.0"
)

# --- Template da Stack Traefik ---
TRAEFIK_STACK_TEMPLATE = """
version: "3.7"

services:
  traefik:
    image: traefik:v2.11.3
    hostname: "{{.Service.Name}}.{{.Task.Slot}}"
    command:
      - "--api.dashboard=true"
      - "--providers.docker.swarmMode=true"
      - "--providers.docker.endpoint=unix:///var/run/docker.sock"
      - "--providers.docker.exposedbydefault=false"
      - "--providers.docker.network=network_swarm_public"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.web.http.redirections.entryPoint.to=websecure"
      - "--entrypoints.web.http.redirections.entryPoint.scheme=https"
      - "--entrypoints.web.http.redirections.entrypoint.permanent=true"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencryptresolver.acme.httpchallenge=true"
      - "--certificatesresolvers.letsencryptresolver.acme.httpchallenge.entrypoint=web"
      - "--certificatesresolvers.letsencryptresolver.acme.email={{LETSENCRYPT_EMAIL}}"
      - "--certificatesresolvers.letsencryptresolver.acme.storage=/etc/traefik/letsencrypt/acme.json"
      - "--log.level=DEBUG"
    deploy:
      placement:
        constraints:
          - node.role == manager
      labels:
        - "traefik.enable=true"
        - "traefik.http.routers.dashboard.rule=Host(`traefik.localhost`) && (PathPrefix(`/api`) || PathPrefix(`/dashboard`))"
        - "traefik.http.routers.dashboard.service=api@internal"
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock:ro"
      - "volume_swarm_certificates:/etc/traefik/letsencrypt"
    networks:
      - network_swarm_public
    ports:
      - target: 80
        published: 80
        mode: host
      - target: 443
        published: 443
        mode: host

volumes:
  volume_swarm_certificates:
    name: volume_swarm_certificates
    driver: local

networks:
  network_swarm_public:
    external: true
    name: network_swarm_public
"""

# --- Funções Auxiliares ---
def execute_ssh_command(ssh_client: paramiko.SSHClient, command: str, logs: List[str], ignore_errors: bool = False) -> str:
    logs.append(f"Executando: {command}")
    stdin, stdout, stderr = ssh_client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()
    output = stdout.read().decode('utf-8').strip()
    error = stderr.read().decode('utf-8').strip()
    if output: logs.append(f"Saída: {output}")
    if error: logs.append(f"Erro: {error}")
    if not ignore_errors and exit_status != 0:
        raise Exception(f"Falha ao executar comando: '{command}'. Código de saída: {exit_status}")
    return output

def get_ssh_connection(server: TraefikDeployDetails) -> paramiko.SSHClient:
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh_client.connect(hostname=server.host, port=22, username="root", password=server.password, timeout=15)
        return ssh_client
    except paramiko.AuthenticationException:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Falha na autenticação. Verifique o IP e a senha.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro de conexão: {e}")

# --- Endpoint da API ---
@app.post("/deploy-traefik", status_code=status.HTTP_200_OK)
def deploy_traefik_stack(server: TraefikDeployDetails):
    logs = []
    ssh_client = None
    sftp = None
    remote_path = "/root/traefik-v2.yaml"
    try:
        ssh_client = get_ssh_connection(server)
        logs.append(f"Conexão com {server.host} estabelecida com sucesso.")

        logs.append(f"Preparando para enviar o arquivo da stack para {remote_path}...")
        stack_content = TRAEFIK_STACK_TEMPLATE.replace("{{LETSENCRYPT_EMAIL}}", server.letsencrypt_email)
        
        sftp = ssh_client.open_sftp()
        with sftp.file(remote_path, 'w') as remote_file:
            remote_file.write(stack_content)
        logs.append("Arquivo da stack enviado com sucesso.")

        execute_ssh_command(ssh_client, "docker pull traefik:v2.11.3", logs)
        deploy_command = f"docker stack deploy --prune --compose-file {remote_path} traefik"
        execute_ssh_command(ssh_client, deploy_command, logs)
        
        return {"message": "Deploy do Traefik concluído com sucesso.", "logs": logs}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        error_detail = {"detail": f"Ocorreu um erro inesperado: {str(e)}", "logs": logs}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)
    finally:
        if sftp: sftp.close()
        if ssh_client: ssh_client.close()