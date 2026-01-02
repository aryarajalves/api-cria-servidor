import os
import json
import paramiko
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import List, Dict

# Carrega as variáveis do arquivo .env para o ambiente de execução.
load_dotenv()

# --- Modelo de Dados de Entrada (Request Body) ---
class ServerDetails(BaseModel):
    host: str = Field(..., description="O endereço IP ou hostname do servidor.", example="192.1.100")
    # RECOMENDAÇÃO: Mudar para autenticação por chave SSH em vez de senha.
    password: str = Field(..., description="A senha do usuário root para a conexão SSH.")

# --- Instância do FastAPI ---
app = FastAPI(
    title="Docker Installer API",
    description="Uma API para instalar o Docker e inicializar o Swarm em um servidor Debian/Ubuntu via SSH.",
    version="1.4.0" # Versão com melhorias de robustez
)

# --- Comandos de Instalação do Docker ---
DOCKER_INSTALL_COMMANDS = [
    "apt-get update",
    "apt-get install -y sudo gnupg2 wget ca-certificates apt-transport-https curl gnupg nano htop",
    "install -m 0755 -d /etc/apt/keyrings",
    "curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg",
    "chmod a+r /etc/apt/keyrings/docker.gpg",
    """echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null""",
    "apt-get update",
    "apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin",
    "systemctl enable docker.service",
    "systemctl enable containerd.service"
]

# --- Função Auxiliar para Executar Comandos ---
def execute_ssh_command(ssh_client: paramiko.SSHClient, command: str, logs: List[str], ignore_errors: bool = False) -> str:
    """
    Executa um comando SSH, registra a saída e os erros, e retorna a saída padrão.
    Lança uma exceção se o comando falhar e ignore_errors for False.
    """
    logs.append(f"Executando: {command}")
    stdin, stdout, stderr = ssh_client.exec_command(command)
    
    # Esta chamada bloqueia a execução até o comando terminar.
    exit_status = stdout.channel.recv_exit_status()
    
    output = stdout.read().decode('utf-8').strip()
    error = stderr.read().decode('utf-8').strip()
    
    if output:
        logs.append(f"Saída: {output}")
    if error:
        logs.append(f"Erro: {error}")

    if not ignore_errors and exit_status != 0:
        raise Exception(f"Falha ao executar comando: '{command}'. Código de saída: {exit_status}")
    
    return output

# --- Endpoint da API ---
@app.post("/install-docker", status_code=status.HTTP_200_OK)
def install_docker_on_server(server: ServerDetails):
    """
    Conecta-se a um servidor, instala o Docker, inicializa o Swarm e cria a rede.
    """
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    logs = []

    try:
        # Conecta ao servidor
        # RECOMENDAÇÃO: Usar `pkey` para autenticação por chave SSH.
        ssh_client.connect(
            hostname=server.host, port=22, username="root", password=server.password, timeout=15
        )
        logs.append(f"Conexão com {server.host} estabelecida com sucesso.")

        # Executa a instalação do Docker
        for command in DOCKER_INSTALL_COMMANDS:
            execute_ssh_command(ssh_client, command, logs)
        
        # Comandos para inicializar o Swarm e criar a rede
        logs.append("Inicializando Docker Swarm...")
        swarm_init_command = f"docker swarm init --advertise-addr={server.host}"
        # Ignoramos erros pois o swarm pode já estar inicializado
        execute_ssh_command(ssh_client, swarm_init_command, logs, ignore_errors=True)
        
        logs.append("Criando a rede overlay...")
        network_create_command = "docker network create --driver=overlay network_swarm_public"
        # Ignoramos erros pois a rede pode já existir
        execute_ssh_command(ssh_client, network_create_command, logs, ignore_errors=True)

        logs.append("Provisionamento do servidor finalizado com sucesso!")
        return {"message": "Provisionamento concluído com sucesso.", "logs": logs}

    except paramiko.AuthenticationException:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Falha na autenticação. Verifique o IP e a senha.")
    except Exception as e:
        error_detail = {
            "detail": f"Ocorreu um erro inesperado: {str(e)}",
            "logs": logs
        }
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)
    finally:
        if ssh_client:
            ssh_client.close()