import os
import json
import time
import requests
import paramiko
import dns.resolver
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import List

# Carrega as variáveis do arquivo .env para o ambiente de execução.
load_dotenv()

# --- Modelos de Dados de Entrada (Request Body) ---
class PortainerDeployDetails(BaseModel):
    host: str = Field(..., description="O endereço IP público do servidor.", example="192.168.1.100")
    password: str = Field(..., description="A senha do usuário root para a conexão SSH.")
    portainer_domain: str = Field(..., description="O domínio que será usado para acessar o Portainer.", example="portainer.meudominio.com")
    # O campo do hash da senha foi removido.
    cloudflare_api_token: str = Field(..., description="Seu token de API da Cloudflare.")
    cloudflare_zone_id: str = Field(..., description="O ID da Zona (domínio) na Cloudflare.")

# --- Instância do FastAPI ---
app = FastAPI(
    title="Portainer Deployer API",
    description="Uma API para configurar o DNS na Cloudflare e implantar o Portainer para configuração manual.",
    version="1.4.2" # Versão com correção de volume
)

# --- Template da Stack Portainer ---
# O comando de senha foi removido para permitir a configuração inicial na interface web.
PORTAINER_STACK_TEMPLATE = """
version: "3.7"

services:
  agent:
    image: portainer/agent:sts
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /var/lib/docker/volumes:/var/lib/docker/volumes
    networks:
      - network_swarm_public
    deploy:
      mode: global
      placement:
        constraints: [node.platform.os == linux]

  portainer:
    image: portainer/portainer-ce:sts
    command: -H tcp://tasks.agent:9001 --tlsskipverify
    volumes:
      - portainer_data:/data
    networks:
      - network_swarm_public
    deploy:
      mode: replicated
      replicas: 1
      placement:
        constraints: [node.role == manager]
      labels:
        - "traefik.enable=true"
        - "traefik.docker.network=network_swarm_public"
        - "traefik.http.routers.portainer.rule=Host(`{{PORTAINER_DOMAIN}}`)"
        - "traefik.http.routers.portainer.entrypoints=websecure"
        - "traefik.http.routers.portainer.tls.certresolver=letsencryptresolver"
        - "traefik.http.services.portainer.loadbalancer.server.port=9000"

networks:
  network_swarm_public:
    external: true
    name: network_swarm_public

volumes:
  portainer_data:
    external: true
    name: portainer_data
"""

# --- Funções Auxiliares ---

def execute_ssh_command(ssh_client: paramiko.SSHClient, command: str, logs: List[str], ignore_errors: bool = False) -> str:
    logs.append(f"Executando comando SSH: {command}")
    stdin, stdout, stderr = ssh_client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()
    output = stdout.read().decode('utf-8').strip()
    error = stderr.read().decode('utf-8').strip()
    if output: logs.append(f"Saída: {output}")
    if error: logs.append(f"Erro: {error}")
    if not ignore_errors and exit_status != 0:
        raise Exception(f"Falha ao executar comando: '{command}'. Código de saída: {exit_status}")
    return output

def get_ssh_connection(server: PortainerDeployDetails) -> paramiko.SSHClient:
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh_client.connect(hostname=server.host, port=22, username="root", password=server.password, timeout=15)
        return ssh_client
    except paramiko.AuthenticationException:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Falha na autenticação. Verifique o IP e a senha.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro de conexão: {e}")

def update_cloudflare_dns(details: PortainerDeployDetails, logs: List[str]):
    logs.append(f"Atualizando DNS para {details.portainer_domain} -> {details.host}")
    api_url = f"https://api.cloudflare.com/client/v4/zones/{details.cloudflare_zone_id}/dns_records"
    headers = {"Authorization": f"Bearer {details.cloudflare_api_token}", "Content-Type": "application/json"}
    response = requests.get(api_url, headers=headers, params={"name": details.portainer_domain})
    response.raise_for_status()
    records = response.json().get("result", [])
    payload = {"type": "A", "name": details.portainer_domain, "content": details.host, "ttl": 1, "proxied": False}
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
    resolver = dns.resolver.Resolver()
    resolver.nameservers = ['8.8.8.8']
    for i in range(30):
        try:
            answers = resolver.resolve(domain, 'A')
            resolved_ip = answers[0].to_text()
            logs.append(f"DNS resolvido para: {resolved_ip}")
            if resolved_ip == target_ip:
                logs.append("Propagação do DNS confirmada!")
                return
        except Exception as e:
            logs.append(f"Aguardando DNS... ({e})")
        time.sleep(10)
    raise Exception("Tempo limite excedido aguardando a propagação do DNS.")

# --- Endpoint da API ---
@app.post("/deploy-portainer", status_code=status.HTTP_200_OK)
def deploy_portainer_stack(server: PortainerDeployDetails):
    logs = []
    ssh_client = None
    sftp = None
    remote_path = "/root/portainer.yaml"
    try:
        update_cloudflare_dns(server, logs)
        wait_for_dns_propagation(server.portainer_domain, server.host, logs)

        ssh_client = get_ssh_connection(server)
        logs.append(f"Conexão SSH com {server.host} estabelecida.")

        logs.append(f"Enviando arquivo da stack para {remote_path}...")
        stack_content = PORTAINER_STACK_TEMPLATE.replace("{{PORTAINER_DOMAIN}}", server.portainer_domain)
        sftp = ssh_client.open_sftp()
        with sftp.file(remote_path, 'w') as f:
            f.write(stack_content)
        logs.append("Arquivo da stack enviado com sucesso.")

        execute_ssh_command(ssh_client, "docker volume create portainer_data", logs, ignore_errors=True)
        execute_ssh_command(ssh_client, "docker pull portainer/portainer-ce:sts", logs)
        execute_ssh_command(ssh_client, "docker pull portainer/agent:sts", logs)
        
        deploy_command = f"docker stack deploy --prune --compose-file {remote_path} portainer"
        execute_ssh_command(ssh_client, deploy_command, logs)

        logs.append("Aguardando 10 segundos para o serviço estabilizar...")
        time.sleep(10)
        
        logs.append("Verificando status do serviço Portainer...")
        status_cmd = 'docker service ls --filter name=portainer_portainer --format "{{.Replicas}}"'
        replica_status = execute_ssh_command(ssh_client, status_cmd, logs)

        if replica_status != "1/1":
            logs.append("!!! ALERTA: O serviço do Portainer não iniciou corretamente. Status: " + replica_status)
            logs.append("Coletando status das tarefas para diagnóstico...")
            # MELHORIA: Usa 'docker service ps' para obter a mensagem de erro exata da falha da tarefa.
            execute_ssh_command(ssh_client, "docker service ps --no-trunc portainer_portainer", logs, ignore_errors=True)
            logs.append("Coletando logs de erro do serviço...")
            execute_ssh_command(ssh_client, "docker service logs --tail 50 portainer_portainer", logs, ignore_errors=True)
            raise Exception("O serviço Portainer falhou ao iniciar. Verifique os logs e o status das tarefas para mais detalhes.")
        
        logs.append("Serviço Portainer iniciado com sucesso (1/1).")
        
        return {"message": "Deploy do Portainer concluído. Acesse o domínio para criar o usuário administrador.", "logs": logs}

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Erro na API da Cloudflare: {e}")
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        error_detail = {"detail": f"Ocorreu um erro inesperado: {str(e)}", "logs": logs}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)
    finally:
        if sftp: sftp.close()
        if ssh_client: ssh_client.close()