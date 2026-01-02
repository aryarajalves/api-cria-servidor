import paramiko
import logging
import os
import tempfile
import requests
from typing import Optional

# Configura o logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_ssh_client(host, username, password, timeout=30):
    """
    Cria e retorna uma conexão SSH usando Paramiko.
    """
    import time
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        logger.info(f"[SSH] Iniciando conexão SSH com {host}")
        logger.info(f"[SSH] Parâmetros: User={username}, Timeout={timeout}s")
        logger.info(f"[SSH] look_for_keys=False, allow_agent=False")
        
        start = time.time()
        client.connect(
            hostname=host, 
            username=username, 
            password=password, 
            timeout=timeout,
            look_for_keys=False,
            allow_agent=False
        )
        elapsed = time.time() - start
        logger.info(f"[SSH] Conexão estabelecida em {elapsed:.2f}s")
        return client
        
    except Exception as e:
        elapsed = time.time() - start if 'start' in locals() else 0
        logger.error(f"[SSH] ERRO após {elapsed:.2f}s: {type(e).__name__}: {str(e)}")
        raise e

def verify_ssh_connection(host, username, password):
    """
    Testa se as credenciais SSH são válidas.
    """
    import time
    start_time = time.time()
    logger.info(f"[VERIFY] Iniciando verificação SSH para {username}@{host}")
    
    try:
        logger.info(f"[VERIFY] Chamando get_ssh_client com timeout=30s")
        client = get_ssh_client(host, username, password, timeout=30)
        
        elapsed = time.time() - start_time
        logger.info(f"[VERIFY] Conexão SSH estabelecida com sucesso em {elapsed:.2f}s")
        
        client.close()
        logger.info(f"[VERIFY] Conexão SSH fechada. Verificação completa.")
        return True
        
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[VERIFY] FALHA na verificação SSH após {elapsed:.2f}s")
        logger.error(f"[VERIFY] Tipo de erro: {type(e).__name__}")
        logger.error(f"[VERIFY] Mensagem de erro: {str(e)}")
        import traceback
        logger.error(f"[VERIFY] Traceback completo:\n{traceback.format_exc()}")
        return False

def run_ssh_command(client, command, timeout=10):
    """
    Executa um comando no servidor remoto via SSH com timeout.
    """
    logger.info(f"CMD: {command}")
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    
    # Define timeout no canal para leitura
    stdout.channel.settimeout(timeout)
    
    try:
        # Aguarda o comando finalizar e pega o status de saída
        # recv_exit_status pode bloquear, mas o timeout do canal deve ajudar
        exit_status = stdout.channel.recv_exit_status()
        
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        if exit_status != 0:
            logger.error(f"ERRO CMD: {command}")
            logger.error(f"STDERR: {error}")
            raise Exception(f"Comando falhou: {error}")
        
        logger.info(f"OUTPUT: {output[:100]}..." if len(output) > 100 else f"OUTPUT: {output}")
        return output

    except Exception as e:
        logger.error(f"Timeout ou erro ao executar '{command}': {e}")
        # Se for timeout, stdout.channel lança timeout
        raise Exception(f"Erro/Timeout ao executar comando: {str(e)}")

# ... (outras funções)

def get_active_stacks(host, username, password):
    """
    Retorna uma lista com os nomes das stacks ativas no servidor remoto.
    """
    client = get_ssh_client(host, username, password)
    try:
        try:
            output = run_ssh_command(client, "docker stack ls --format '{{.Name}}'")
            stacks = [s.strip() for s in output.strip().splitlines() if s.strip()]
            print(f"DEBUG: Stacks ativas no servidor {host}: {stacks}", flush=True)
            return stacks
        except Exception as e:
            print(f"ERRO ao listar stacks: {e}", flush=True)
            return []
    finally:
        client.close()

def check_stack_exists(host, username, password, stack_name):
    """
    Verifica se a stack Docker já existe no servidor remoto.
    Retorna True se existir, False caso contrário.
    """
    stacks = get_active_stacks(host, username, password)
    exists = stack_name in stacks
    print(f"CHECK STACK '{stack_name}': {exists}", flush=True)
    return exists

def check_docker_installed(host, username, password):
    """
    Verifica se o Docker já está instalado no servidor remoto.
    Retorna a string de versão se instalado, None caso contrário.
    """
    client = get_ssh_client(host, username, password)
    try:
        # Usamos um bloco try-except porque run_ssh_command lança uma exceção se o comando falhar
        try:
            version = run_ssh_command(client, "docker --version")
            return version
        except Exception:
            return None
    finally:
        client.close()

def install_docker(host, username, password):
    """
    Instala o Docker em um sistema remoto baseado em Debian via SSH.
    """
    commands = [
        "sudo apt-get update",
        "sudo apt install -y sudo gnupg2 wget ca-certificates apt-transport-https curl gnupg nano htop",
        "sudo install -m 0755 -d /etc/apt/keyrings",
        "curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg || true", # || true para evitar erro se existir
        "sudo chmod a+r /etc/apt/keyrings/docker.gpg",
        'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null',
        "sudo apt-get update",
        "sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin",
        "sudo systemctl enable docker.service",
        "sudo systemctl enable containerd.service"
    ]

    client = get_ssh_client(host, username, password)
    try:
        logger.info(f"Iniciando instalação do Docker em {host}...")
        for cmd in commands:
            run_ssh_command(client, cmd)
        logger.info("Instalação do Docker concluída com sucesso.")
        return {"status": "success", "message": "Docker instalado com sucesso"}
    finally:
        client.close()

def upgrade_docker_engine(host, username, password):
    """
    Atualiza o Docker Engine no servidor remoto via SSH.
    """
    commands = [
        "sudo apt-get update",
        "sudo DEBIAN_FRONTEND=noninteractive apt-get install --only-upgrade -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
    ]

    client = get_ssh_client(host, username, password)
    try:
        logger.info(f"Iniciando atualização do Docker em {host}...")
        for cmd in commands:
            run_ssh_command(client, cmd)
        logger.info("Atualização do Docker concluída com sucesso.")
        return {"status": "success", "message": "Docker atualizado com sucesso"}
    finally:
        client.close()

def check_swarm_active(host, username, password):
    """
    Verifica se o Docker Swarm já está ativo no servidor remoto.
    Retorna True se ativo, False caso contrário.
    """
    client = get_ssh_client(host, username, password)
    try:
        try:
            # Verifica o estado do Swarm
            output = run_ssh_command(client, "docker info --format '{{.Swarm.LocalNodeState}}'")
            return output.strip() == "active"
        except Exception:
            return False
    finally:
        client.close()

def init_swarm(host, username, password, advertise_addr):
    """
    Inicializa o Docker Swarm em um servidor remoto.
    """
    client = get_ssh_client(host, username, password)
    try:
        logger.info(f"Inicializando Swarm em {host} ({advertise_addr})...")
        try:
            run_ssh_command(client, f"docker swarm init --advertise-addr {advertise_addr}")
            return {"status": "success", "message": "Swarm inicializado"}
        except Exception as e:
            if "This node is already part of a swarm" in str(e):
                logger.info("Nó já faz parte de um swarm.")
                return {"status": "success", "message": "Nó já faz parte de um swarm"}
            raise e
    finally:
        client.close()

def check_network_exists(host, username, password, network_name):
    """
    Verifica se a rede Docker já existe no servidor remoto.
    Retorna True se existir, False caso contrário.
    """
    client = get_ssh_client(host, username, password)
    try:
        try:
            # Lista as redes filtrando pelo nome exato
            output = run_ssh_command(client, f"docker network ls --filter name=^{network_name}$ --format '{{{{.Name}}}}'")
            return output.strip() == network_name
        except Exception:
            return False
    finally:
        client.close()

def create_network(host, username, password, network_name):
    """
    Cria uma rede overlay Docker em um servidor remoto.
    """
    client = get_ssh_client(host, username, password)
    try:
        logger.info(f"Criando rede {network_name} em {host}...")
        try:
            run_ssh_command(client, f"docker network create --driver overlay --attachable {network_name}")
            return {"status": "success", "message": f"Rede {network_name} criada"}
        except Exception as e:
             if "network with name" in str(e) and "already exists" in str(e):
                 logger.info(f"Rede {network_name} já existe.")
                 return {"status": "success", "message": f"Rede {network_name} já existe"}
             raise e
    finally:
        client.close()



def deploy_stack_remote(client, stack_name, stack_content):
    """
    Faz o deploy de uma stack Docker em um servidor remoto.
    """
    logger.info(f"Fazendo deploy da stack {stack_name}...")
    
    # Precisamos transferir o arquivo para o servidor remoto
    sftp = client.open_sftp()
    # Salva diretamente na pasta /root/
    remote_path = f"/root/{stack_name}.yml"
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False, encoding='utf-8') as temp_file:
        temp_file.write(stack_content)
        temp_file_path = temp_file.name
    
    try:
        sftp.put(temp_file_path, remote_path)
        run_ssh_command(client, f"docker stack deploy -c {remote_path} {stack_name}")
        return {"status": "success", "message": f"Stack {stack_name} deployada"}
    finally:
        sftp.close()
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

def install_traefik(host, username, password, email):
    """
    Faz o deploy da stack do Traefik em um servidor remoto.
    """
    stack_path = os.path.join("app", "stack", "stacks", "traefik.yml")
    
    if not os.path.exists(stack_path):
        raise FileNotFoundError(f"Arquivo de stack não encontrado: {stack_path}")

    with open(stack_path, "r") as f:
        stack_content = f.read()

    # Substitui o placeholder de email
    stack_content = stack_content.replace("{email}", email)
        
    client = get_ssh_client(host, username, password)
    try:
        return deploy_stack_remote(client, "traefik", stack_content)
    finally:
        client.close()

def install_portainer(host, username, password, portainer_host):
    """
    Faz o deploy da stack do Portainer em um servidor remoto.
    """
    stack_path = os.path.join("app", "stack", "stacks", "portainer.yml")
    
    if not os.path.exists(stack_path):
        raise FileNotFoundError(f"Arquivo de stack não encontrado: {stack_path}")

    with open(stack_path, "r") as f:
        stack_content = f.read()
        
    # Substitui o placeholder pelo host real
    stack_content = stack_content.replace("{{PORTAINER_HOST}}", portainer_host)
        
    client = get_ssh_client(host, username, password)
    try:
        return deploy_stack_remote(client, "portainer", stack_content)
    finally:
        client.close()

def update_docker_version_config(host, username, password):
    """
    Aplica a correção de versão da API do Docker para compatibilidade com Traefik/Portainer.
    Cria um override no systemd definindo DOCKER_MIN_API_VERSION=1.24.
    """
    client = get_ssh_client(host, username, password)
    try:
        logger.info(f"Aplicando correção de versão da API do Docker em {host}...")
        
        # 1. Cria o diretório de override se não existir
        run_ssh_command(client, "sudo mkdir -p /etc/systemd/system/docker.service.d")
        
        # 2. Cria o arquivo de configuração override
        # Usamos echo com tee para escrever no arquivo com permissões de sudo
        override_content = "[Service]\nEnvironment=DOCKER_MIN_API_VERSION=1.24"
        cmd_create_file = f'echo -e "{override_content}" | sudo tee /etc/systemd/system/docker.service.d/override.conf'
        run_ssh_command(client, cmd_create_file)
        
        # 3. Recarrega o daemon do systemd
        run_ssh_command(client, "sudo systemctl daemon-reexec")
        run_ssh_command(client, "sudo systemctl daemon-reload")
        
        # 4. Reinicia o serviço do Docker
        run_ssh_command(client, "sudo systemctl restart docker")
        
        logger.info("Correção aplicada e Docker reiniciado com sucesso.")
        return {"status": "success", "message": "Configuração do Docker atualizada com sucesso"}
    finally:
        client.close()

def install_redis(host, username, password):
    """
    Faz o deploy da stack do Redis em um servidor remoto via SSH.
    """
    stack_path = os.path.join("app", "stack", "stacks", "redis.yml")
    
    if not os.path.exists(stack_path):
        raise FileNotFoundError(f"Arquivo de stack não encontrado: {stack_path}")

    with open(stack_path, "r") as f:
        stack_content = f.read()
        
    client = get_ssh_client(host, username, password)
    try:
        return deploy_stack_remote(client, "redis", stack_content)
    finally:
        client.close()

def install_redis_via_portainer(host, username, password, api_key=None):
    """
    Faz o deploy da stack do Redis usando a API do Portainer VIA SSH (Localhost).
    Isso evita problemas de firewall/portas fechadas (9000/9443).
    """
    import json
    import time
    import random
    
    stack_path = os.path.join("app", "stack", "stacks", "redis.yml")
    if not os.path.exists(stack_path):
        raise FileNotFoundError(f"Arquivo de stack não encontrado: {stack_path}")

    with open(stack_path, "r") as f:
        stack_content = f.read()

    client = get_ssh_client(host, username, password)
    
    try:
        # Helper interno para rodar CURL e parsear JSON
        def curl_request(method, endpoint, headers_dict, data_dict=None):
            # Use 127.0.0.1 para evitar problemas com IPv6 no localhost
            url = f"http://127.0.0.1:9000/api{endpoint}"
            
            # Monta headers
            header_args = []
            for k, v in headers_dict.items():
                header_args.append(f'-H "{k}: {v}"')
            header_str = " ".join(header_args)
            
            # Arquivos temporarios
            remote_base = f"/tmp/portainer_{int(time.time())}_{random.randint(1000,9999)}"
            remote_json_path = f"{remote_base}.json"
            remote_out_path = f"{remote_base}.out"
            
            # Se tiver dados, salva em arquivo temp remoto
            data_arg = ""
            if data_dict:
                try:
                    sftp = client.open_sftp()
                    with sftp.file(remote_json_path, 'w') as f:
                        f.write(json.dumps(data_dict))
                    sftp.close()
                except Exception as e:
                    logger.error(f"Erro no upload SFTP: {e}")
                    raise e
                
                data_arg = f"-d @{remote_json_path}"
                cleanup_files = f"{remote_json_path} {remote_out_path}"
            else:
                cleanup_files = f"{remote_out_path}"

            # Monta comando CURL SIMPLES
            # -o {remote_out_path}: Salva BODY (JSON)
            # --max-time 30: Timeout interno do curl
            # -s -S: Silent mas mostra erros
            cmd = f"curl --max-time 30 -s -S -X {method} {header_str} -H 'Content-Type: application/json' {data_arg} '{url}' -o {remote_out_path}"
            
            print(f"DEBUG: [SSH] Enviando comando: {method} {endpoint}")
            
            # Executa limpo
            stdin, stdout, stderr = client.exec_command(cmd)
            stdin.close()
            
            # Agora é seguro esperar
            print(f"DEBUG: [SSH] Aguardando termino...")
            exit_status = stdout.channel.recv_exit_status()
            print(f"DEBUG: [SSH] Terminou. Exit: {exit_status}")
            
            # Lê stderr se tiver
            err_log = stderr.read().decode('utf-8')

            if exit_status != 0:
                 raise Exception(f"CURL Failed with Exit Code {exit_status}. Stderr: {err_log[-500:]}")
            
            # Lê o arquivo de resposta
            print(f"DEBUG: [SSH] Lendo resposta de {remote_out_path}...")
            try:
                stdin_cat, stdout_cat, stderr_cat = client.exec_command(f"cat {remote_out_path}")
                out_content = stdout_cat.read().decode('utf-8').strip()
            except Exception as e:
                raise Exception(f"Falha ao ler output file: {e}")
                
            # Limpeza
            client.exec_command(f"rm {cleanup_files}")
            
            try:
                if not out_content: return {}
                return json.loads(out_content)
            except json.JSONDecodeError:
                 if "404" in out_content: raise Exception("Portainer API 404 Not Found")
                 if "401" in out_content: raise Exception("Portainer API 401 Unauthorized")
                 if "Bad Request" in out_content: raise Exception(f"Portainer 400 Bad Request: {out_content}")
                 raise Exception(f"Falha ao parsear JSON: {out_content[:200]}...")

        # 1. Autenticação (Se não tiver API Key)
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key
        else:
            logger.info("Autenticando no Portainer (Localhost) com credenciais internas...")
            auth_resp = curl_request("POST", "/auth", {}, {"Username": "admin", "Password": "admin12345"})
            if not auth_resp.get("jwt"):
                 raise Exception(f"Falha na autenticação: {auth_resp}")
            headers["Authorization"] = f"Bearer {auth_resp['jwt']}"

        # 2. Buscar Endpoint ID
        logger.info("Buscando Endpoint ID...")
        endpoints = curl_request("GET", "/endpoints", headers)
        endpoint_id = None
        for ep in endpoints:
            if ep.get("Status") == 1: # Up
                endpoint_id = ep.get("Id")
                break
        
        if not endpoint_id:
            raise Exception("Nenhum endpoint ativo encontrado no Portainer.")

        # 3. Verificar se Stack existe
        logger.info("Verificando stacks existentes...")
        stacks = curl_request("GET", "/stacks", headers)
        for stack in stacks:
            if stack.get("Name") == "redis":
                 return {"status": "success", "message": "Stack Redis já existe no Portainer."}

        # 4. Deploy da Stack
        logger.info(f"Criando Stack Redis no Endpoint {endpoint_id}...")
        
        # Precisamos do SwarmID
        docker_info = curl_request("GET", f"/endpoints/{endpoint_id}/docker/info", headers)
        swarm_id = docker_info.get("Swarm", {}).get("Cluster", {}).get("ID")
        
        payload = {
            "Name": "redis",
            "StackFileContent": stack_content,
            "SwarmID": swarm_id or "placeholder"
        }
        
        logger.info(f"DEBUG: Payload size: {len(json.dumps(payload))} bytes")
        
        # Query Params na URL para create stack
        create_url = f"/stacks?type=1&method=string&endpointId={endpoint_id}"
        
        deploy_resp = curl_request("POST", create_url, headers, payload)
        
        if deploy_resp.get("Id"):
             return {"status": "success", "message": "Redis instalado com sucesso via Portainer (Localhost)!"}
        else:
             # Tenta ler mensagem de erro
             raise Exception(f"Erro no deploy: {deploy_resp}")

    finally:
        client.close()

def install_postgres(host, username, password, postgres_password):
    """
    Faz o deploy da stack do Postgres em um servidor remoto via SSH.
    Substitui o placeholder ${POSTGRES_PASSWORD} pela senha fornecida.
    """
    stack_path = os.path.join("app", "stack", "stacks", "postgres.yml")
    
    if not os.path.exists(stack_path):
        raise FileNotFoundError(f"Arquivo de stack não encontrado: {stack_path}")

    with open(stack_path, "r") as f:
        stack_content = f.read()
    
    # Substitui o placeholder pela senha real
    stack_content = stack_content.replace("${POSTGRES_PASSWORD}", postgres_password)
        
    client = get_ssh_client(host, username, password)
    try:
        return deploy_stack_remote(client, "postgres", stack_content)
    finally:
        client.close()

def install_rabbitmq(host, username, password, rabbit_user, rabbit_password, rabbit_base_url):
    """
    Faz o deploy da stack do RabbitMQ em um servidor remoto via SSH.
    Substitui os placeholders {Usuario_Rabbit}, {Senha_Rabbit} e {BaseUrl_Rabbit}.
    """
    stack_path = os.path.join("app", "stack", "stacks", "rabbit.yml")
    
    if not os.path.exists(stack_path):
        raise FileNotFoundError(f"Arquivo de stack não encontrado: {stack_path}")

    with open(stack_path, "r") as f:
        stack_content = f.read()
    
    # Remove https:// se vier na URL
    rabbit_base_url_clean = rabbit_base_url.replace("https://", "").replace("http://", "")

    # Substitui os placeholders
    stack_content = stack_content.replace("{Usuario_Rabbit}", rabbit_user)
    stack_content = stack_content.replace("{Senha_Rabbit}", rabbit_password)
    stack_content = stack_content.replace("{BaseUrl_Rabbit}", rabbit_base_url_clean)
        
    client = get_ssh_client(host, username, password)
    try:
        return deploy_stack_remote(client, "rabbitmq", stack_content)
    finally:
        client.close()

def install_minio(host, username, password, minio_user, minio_password, minio_base_url_private, minio_base_url_public):
    """
    Faz o deploy da stack do Minio em um servidor remoto via SSH.
    Substitui os placeholders {Usuario_Minio}, {Senha_Minio}, {Console_Domain} e {Domain}.
    
    Args:
        minio_base_url_private: Console domain (e.g., console.minio.domain.com)
        minio_base_url_public: S3 API domain (e.g., s3.domain.com)
    """
    stack_path = os.path.join("app", "stack", "stacks", "minio.yml")
    
    if not os.path.exists(stack_path):
        raise FileNotFoundError(f"Arquivo de stack não encontrado: {stack_path}")

    with open(stack_path, "r") as f:
        stack_content = f.read()
    
    console_domain = minio_base_url_private   # Ex: privadotesteary02.aryaraj.shop
    api_domain = minio_base_url_public        # Ex: s3testeary02.aryaraj.shop

    # Substitui os placeholders
    stack_content = stack_content.replace("{Usuario_Minio}", minio_user)
    stack_content = stack_content.replace("{Senha_Minio}", minio_password)
    stack_content = stack_content.replace("{Console_Domain}", console_domain)
    stack_content = stack_content.replace("{Domain}", api_domain)
        
    client = get_ssh_client(host, username, password)
    try:
        return deploy_stack_remote(client, "minio", stack_content)
    finally:
        client.close()

def create_postgres_database(client, db_name):
    """
    Cria um banco de dados no container do Postgres, se não existir.
    """
    logger.info(f"Verificando/Criando banco de dados '{db_name}' no Postgres...")
    
    # Encontra o ID do container do Postgres
    # Assume que o nome do serviço é postgres_postgres (stack_service) e está rodando no nó atual (manager)
    # O filtro name=postgres_postgres deve pegar qualquer réplica
    get_container_cmd = "docker ps -q -f name=postgres_postgres | head -n 1"
    container_id = run_ssh_command(client, get_container_cmd)
    
    if not container_id:
        logger.warning("Container do Postgres não encontrado. Não foi possível criar o banco de dados.")
        return

    # Comando para verificar se o banco existe
    check_db_cmd = f'docker exec {container_id} psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname=\'{db_name}\'"'
    try:
        exists = run_ssh_command(client, check_db_cmd)
        if exists.strip() == "1":
            logger.info(f"Banco de dados '{db_name}' já existe.")
            return
    except Exception:
        pass # Se der erro, tenta criar mesmo assim

    # Comando para criar o banco
    create_db_cmd = f'docker exec {container_id} psql -U postgres -c "CREATE DATABASE {db_name};"'
    try:
        run_ssh_command(client, create_db_cmd)
        logger.info(f"Banco de dados '{db_name}' criado com sucesso.")
    except Exception as e:
        if "already exists" in str(e):
            logger.info(f"Banco de dados '{db_name}' já existe.")
        else:
            logger.error(f"Erro ao criar banco de dados: {e}")
            raise e

def install_baserow(host, username, password, baserow_base_url, postgres_password):
    """
    Faz o deploy da stack do Baserow em um servidor remoto via SSH.
    Cria o banco de dados 'baserow' no Postgres antes do deploy.
    Substitui os placeholders {BaseUrl_Baserow} e {Senha_Baserow}.
    """
    stack_path = os.path.join("app", "stack", "stacks", "baserow.yml")
    
    if not os.path.exists(stack_path):
        raise FileNotFoundError(f"Arquivo de stack não encontrado: {stack_path}")

    with open(stack_path, "r") as f:
        stack_content = f.read()
    
    # Remove https:// se vier na URL, pois o arquivo yml já adiciona onde precisa
    baserow_base_url_clean = baserow_base_url.replace("https://", "").replace("http://", "")

    # Substitui os placeholders
    stack_content = stack_content.replace("{BaseUrl_Baserow}", baserow_base_url_clean)
    stack_content = stack_content.replace("{Senha_Baserow}", postgres_password)
        
    client = get_ssh_client(host, username, password)
    try:
        # 1. Cria o banco de dados
        create_postgres_database(client, "baserow")
        
        # 2. Faz o deploy da stack
        return deploy_stack_remote(client, "baserow", stack_content)
    finally:
        client.close()

def install_chatwoot(host, username, password, postgres_password, minio_user, minio_password, minio_base_url_public, chatwoot_base_url):
    """
    Faz o deploy das stacks do Chatwoot (Admin e Sidekiq) em um servidor remoto via SSH.
    Executa 'bundle exec rails db:chatwoot_prepare' após o deploy.
    """
    # Limpa as URLs
    minio_base_url_public_clean = minio_base_url_public.replace("https://", "").replace("http://", "")
    chatwoot_base_url_clean = chatwoot_base_url.replace("https://", "").replace("http://", "")
    
    client = get_ssh_client(host, username, password)
    try:
        # 1. Cria o banco de dados
        create_postgres_database(client, "chatwoot")

        # 2. Deploy do Chatwoot Admin
        stack_path_admin = os.path.join("app", "stack", "stacks", "chatwoot_admin.yml")
        if not os.path.exists(stack_path_admin):
            raise FileNotFoundError(f"Arquivo de stack não encontrado: {stack_path_admin}")

        with open(stack_path_admin, "r") as f:
            content_admin = f.read()
        
        content_admin = content_admin.replace("{Senha_Postgres}", postgres_password)
        content_admin = content_admin.replace("{Usuario_Minio}", minio_user)
        content_admin = content_admin.replace("{Senha_Minio}", minio_password)
        content_admin = content_admin.replace("{BaseUrl_Publica_Minio}", minio_base_url_public_clean)
        content_admin = content_admin.replace("{BaseUrl_chatwoot}", chatwoot_base_url_clean) # Env var
        content_admin = content_admin.replace("{BaseUrl_Chatwoot}", chatwoot_base_url_clean) # Traefik label
        
        deploy_stack_remote(client, "chatwoot_admin", content_admin)
        
        # 2. Deploy do Chatwoot Sidekiq
        stack_path_sidekiq = os.path.join("app", "stack", "stacks", "chatwoot_sidekiq.yml")
        if not os.path.exists(stack_path_sidekiq):
            raise FileNotFoundError(f"Arquivo de stack não encontrado: {stack_path_sidekiq}")

        with open(stack_path_sidekiq, "r") as f:
            content_sidekiq = f.read()
            
        content_sidekiq = content_sidekiq.replace("{Senha_Postgres}", postgres_password)
        content_sidekiq = content_sidekiq.replace("{Usuario_Minio}", minio_user)
        content_sidekiq = content_sidekiq.replace("{Senha_Minio}", minio_password)
        content_sidekiq = content_sidekiq.replace("{BaseUrl_Publica_Minio}", minio_base_url_public_clean)
        content_sidekiq = content_sidekiq.replace("{BaseUrl_chatwoot}", chatwoot_base_url_clean)
        
        deploy_stack_remote(client, "chatwoot_sidekiq", content_sidekiq)
        
        # 3. Executar prepare database
        logger.info("Aguardando containers iniciarem para rodar a migração do banco...")
        import time
        time.sleep(10) # Espera um pouco para o serviço ser criado
        
        # Tenta encontrar o container do admin
        # O nome do serviço é chatwoot_admin_chatwoot_admin
        get_container_cmd = "docker ps -q -f name=chatwoot_admin_chatwoot_admin | head -n 1"
        
        # Loop para tentar pegar o container ID (pode demorar para subir)
        container_id = None
        for _ in range(12): # Tenta por 1 minuto (12 * 5s)
            container_id = run_ssh_command(client, get_container_cmd).strip()
            if container_id:
                break
            logger.info("Aguardando container do Chatwoot Admin subir...")
            time.sleep(5)
            
        if container_id:
            logger.info(f"Container encontrado: {container_id}. Executando db:chatwoot_prepare...")
            prepare_cmd = f"docker exec {container_id} bundle exec rails db:chatwoot_prepare"
            try:
                run_ssh_command(client, prepare_cmd)
                logger.info("Migração do Chatwoot concluída com sucesso.")
            except Exception as e:
                logger.error(f"Erro ao rodar migração do Chatwoot: {e}")
                # Não lança exceção aqui para não invalidar o deploy que já foi feito, mas loga o erro
        else:
            logger.warning("Não foi possível encontrar o container do Chatwoot Admin para rodar a migração.")

        return {"status": "success", "message": "Chatwoot instalado e configurado com sucesso."}

    finally:
        client.close()

def restart_stack_services(host, username, password, stack_name):
    """
    Reinicia todos os serviços de uma stack específica forçando um update.
    Equivalente a 'docker service update --force <service_name>' para cada serviço da stack.
    """
    client = get_ssh_client(host, username, password)
    try:
        # 1. Lista os serviços da stack
        logger.info(f"Listando serviços da stack '{stack_name}' para reinício...")
        cmd_list = f"docker stack services {stack_name} --format '{{{{.Name}}}}'"
        output = run_ssh_command(client, cmd_list)
        services = [s.strip() for s in output.strip().splitlines() if s.strip()]
        
        if not services:
            logger.warning(f"Nenhum serviço encontrado para a stack '{stack_name}'.")
            return {"status": "warning", "message": f"Nenhum serviço encontrado para a stack '{stack_name}'"}

        logger.info(f"Serviços encontrados: {services}")
        
        # 2. Reinicia cada serviço
        results = []
        for service in services:
            logger.info(f"Reiniciando serviço '{service}'...")
            cmd_update = f"docker service update --force {service}"
            try:
                run_ssh_command(client, cmd_update)
                results.append(f"Serviço '{service}' reiniciado com sucesso.")
            except Exception as e:
                logger.error(f"Erro ao reiniciar serviço '{service}': {e}")
                results.append(f"Erro ao reiniciar '{service}': {str(e)}")
        
    finally:
        client.close()

def install_n8n(host, username, password, postgres_password, n8n_host, n8n_webhook_url):
    """
    Instala a stack do N8N (Editor, Webhook, Worker).
    1. Cria o banco de dados 'n8n_queue' no Postgres.
    2. Faz o deploy das 3 stacks.
    """
    client = get_ssh_client(host, username, password)
    try:
        # 1. Cria o banco de dados
        create_postgres_database(client, "n8n_queue")

        # Limpa URLs
        n8n_host_clean = n8n_host.replace("https://", "").replace("http://", "").strip("/")
        n8n_webhook_url_clean = n8n_webhook_url.replace("https://", "").replace("http://", "").strip("/")

        # 2. Deploy do N8N Editor
        stack_path_editor = os.path.join("app", "stack", "stacks", "n8n_editor.yml")
        if not os.path.exists(stack_path_editor):
             raise FileNotFoundError(f"Arquivo de stack não encontrado: {stack_path_editor}")
        
        with open(stack_path_editor, "r", encoding="utf-8") as f:
            content_editor = f.read()
        
        content_editor = content_editor.replace("{Senha_Postgres}", postgres_password)
        content_editor = content_editor.replace("{N8N_HOST}", n8n_host_clean)
        content_editor = content_editor.replace("{N8N_Webhook}", n8n_webhook_url_clean)
        
        deploy_stack_remote(client, "n8n_editor", content_editor)

        # 3. Deploy do N8N Webhook
        stack_path_webhook = os.path.join("app", "stack", "stacks", "n8n_webhook.yml")
        if not os.path.exists(stack_path_webhook):
             raise FileNotFoundError(f"Arquivo de stack não encontrado: {stack_path_webhook}")

        with open(stack_path_webhook, "r", encoding="utf-8") as f:
            content_webhook = f.read()
            
        content_webhook = content_webhook.replace("{Senha_Postgres}", postgres_password)
        content_webhook = content_webhook.replace("{N8N_HOST}", n8n_host_clean)
        content_webhook = content_webhook.replace("{N8N_Webhook}", n8n_webhook_url_clean)

        deploy_stack_remote(client, "n8n_webhook", content_webhook)

        # 4. Deploy do N8N Worker
        stack_path_worker = os.path.join("app", "stack", "stacks", "n8n_worker.yml")
        if not os.path.exists(stack_path_worker):
             raise FileNotFoundError(f"Arquivo de stack não encontrado: {stack_path_worker}")

        with open(stack_path_worker, "r", encoding="utf-8") as f:
            content_worker = f.read()

        content_worker = content_worker.replace("{Senha_Postgres}", postgres_password)
        content_worker = content_worker.replace("{N8N_HOST}", n8n_host_clean)
        content_worker = content_worker.replace("{N8N_Webhook}", n8n_webhook_url_clean)

        deploy_stack_remote(client, "n8n_worker", content_worker)

        return {"status": "success", "message": "N8N (Editor, Webhook, Worker) instalado com sucesso."}

    finally:
        client.close()

def get_stack_services(client, stack_name):
    """
    Retorna uma lista dos nomes dos serviços de uma stack.
    """
    cmd = f"docker stack services {stack_name} --format '{{{{.Name}}}}'"
    output = run_ssh_command(client, cmd)
    return [s.strip() for s in output.strip().splitlines() if s.strip()]

def get_service_env_vars(client, service_name):
    """
    Retorna um dicionário com as variáveis de ambiente de um serviço.
    """
    # Formato retornado é ["VAR=VAL", "VAR2=VAL2"]
    cmd = f"docker service inspect {service_name} --format '{{{{json .Spec.TaskTemplate.ContainerSpec.Env}}}}'"
    try:
        output = run_ssh_command(client, cmd)
        import json
        env_list = json.loads(output)
        if not env_list:
            return {}
        
        env_dict = {}
        for item in env_list:
            if "=" in item:
                key, value = item.split("=", 1)
                env_dict[key] = value
        return env_dict
    except Exception as e:
        logger.error(f"Erro ao ler env vars de {service_name}: {e}")
        return {}

def get_stack_env_vars(host, username, password, stack_name):
    """
    Retorna as variáveis de ambiente consolidadas da stack.
    Pega do primeiro serviço encontrado, assumindo que compartilham as principais configs.
    """
    client = get_ssh_client(host, username, password)
    try:
        services = get_stack_services(client, stack_name)
        if not services:
            return {}
        
        # Pega do primeiro serviço (geralmente o principal)
        return get_service_env_vars(client, services[0])
    finally:
        client.close()

def update_stack_env_vars(host, username, password, stack_name, env_vars):
    """
    Atualiza as variáveis de ambiente de TODOS os serviços da stack.
    env_vars é um dict {'VAR': 'VAL'}.
    """
    client = get_ssh_client(host, username, password)
    try:
        services = get_stack_services(client, stack_name)
        if not services:
            raise Exception(f"Nenhum serviço encontrado para a stack {stack_name}")

        # Monta a string de argumentos --env-add
        env_args = []
        for key, value in env_vars.items():
            # Escapa aspas se necessário
            env_args.append(f'--env-add "{key}={value}"')
        
        env_args_str = " ".join(env_args)
        
        for service in services:
            logger.info(f"Atualizando variáveis em {service}...")
            cmd = f"docker service update {env_args_str} {service}"
            run_ssh_command(client, cmd)
            
        return {"status": "success", "message": f"Variáveis atualizadas em {len(services)} serviços da stack {stack_name}"}
    finally:
        client.close()

def update_docker_version_config(host, username, password):
    """
    Configura DOCKER_MIN_API_VERSION=1.24 no systemd override e reinicia o Docker.
    """
    client = get_ssh_client(host, username, password)
    try:
        logger.info(f"Aplicando correção de versão da API do Docker em {host}...")
        
        # 1. Criar diretório se não existir
        run_ssh_command(client, "sudo mkdir -p /etc/systemd/system/docker.service.d")
        
        # 2. Criar arquivo de override
        override_content = '[Service]\nEnvironment="DOCKER_MIN_API_VERSION=1.24"'
        cmd_create_file = f'echo \'{override_content}\' | sudo tee /etc/systemd/system/docker.service.d/override.conf'
        run_ssh_command(client, cmd_create_file)
        
        # 3. Reload e Restart
        run_ssh_command(client, "sudo systemctl daemon-reload")
        run_ssh_command(client, "sudo systemctl restart docker")
        
        # 4. Verificar (comando solicitado pelo usuário)
        output = run_ssh_command(client, "systemctl show --property=Environment docker")
        logger.info(f"Verificação de ambiente Docker: {output.strip()}")
        
        return {"status": "success", "message": "Configuração do Docker atualizada com sucesso"}
    finally:
        client.close()

def get_full_system_status(host, username, password):
    """
    Realiza todas as verificações de estado do sistema em UMA ÚNICA conexão SSH.
    Isso otimiza muito o tempo de resposta dibandingkan fazer 5 conexões separadas.
    """
    client = get_ssh_client(host, username, password, timeout=10)
    status = {
        "docker": None,
        "swarm": False,
        "network": False,
        "ctop": False,
        "active_stacks": []
    }
    
    try:
        # 1. Check Docker
        try:
            # Reutiliza o cliente para rodar comando
            output = run_ssh_command(client, "docker --version", timeout=5)
            status["docker"] = output.strip()
        except:
            return status # Se não tem docker, retorna tudo false/vazio

        # 2. Check Swarm
        try:
            output = run_ssh_command(client, "docker info --format '{{.Swarm.LocalNodeState}}'", timeout=5)
            status["swarm"] = (output.strip() == "active")
        except:
            pass

        # 3. Check Ctop (Execution based)
        try:
            # Run ctop --help to check if command exists (avoids TUI hang)
            # Add /usr/local/bin to PATH ensuring we find it if it's there
            cmd = "export PATH=$PATH:/usr/local/bin; ctop --help"
            stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
            out = stdout.read().decode('utf-8')
            err = stderr.read().decode('utf-8')
            full_req = (out + err).lower()

            # Debug log to see exactly what is returned
            logger.info(f"CTOP Check Output: '{full_req}'")

            # Rigid check for shell error. "not found" is too broad (can be config not found)
            if "command not found" in full_req or (len(full_req.strip()) > 0 and "not found" in full_req and "sh:" in full_req):
                status["ctop"] = False
            else:
                status["ctop"] = True
                
        except Exception as e:
             logger.warning(f"Ctop check exception: {e}")
             # Timeout or connection error -> Assume False
             pass

        # 4. Check Network & Stacks (Only if Swarm is active usually, but we check if docker exists)
        if status["swarm"]:
            try:
                # Check Network
                net_cmd = "docker network ls --filter name=^network_swarm_public$ --format '{{.Name}}'"
                output = run_ssh_command(client, net_cmd, timeout=5)
                status["network"] = (output.strip() == "network_swarm_public")
                
                # Check Stacks
                stack_cmd = "docker stack ls --format '{{.Name}}'"
                output = run_ssh_command(client, stack_cmd, timeout=5)
                status["active_stacks"] = [s.strip() for s in output.strip().splitlines() if s.strip()]
            except:
                pass
                
    except Exception as e:
        logger.error(f"Erro no check em lote: {e}")
    finally:
        client.close()
        
    return status


def check_ctop_installed(host, username, password):
    """
    Verifica se o Ctop está instalado no servidor remoto.
    Executa 'ctop --help' e verifica se retorna 'command not found'.
    """
    client = get_ssh_client(host, username, password)
    try:
        try:
            # User request: Check if running 'ctop' returns 'command not found'.
            # We use --help to avoid entering the TUI if it IS installed.
            # Add /usr/local/bin to PATH
            cmd = "export PATH=$PATH:/usr/local/bin; ctop --help"
            stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
            
            # Combine outputs to check for the shell error message
            out = stdout.read().decode('utf-8')
            err = stderr.read().decode('utf-8')
            full_output = (out + err).lower()

            if "command not found" in full_output or "not found" in full_output:
                 return False
            
            # If it didn't say "not found", assumes it is installed
            return True

        except Exception:
            # Communication error or timeout
            return False
    finally:
        client.close()


def install_ctop(host, username, password):
    """
    Instala o Ctop (container monitoring tool) no servidor remoto via SSH.
    """
    commands = [
        "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl gnupg lsb-release",
        "curl -fsSL https://azlux.fr/repo.gpg.key | sudo gpg --dearmor --batch --yes -o /usr/share/keyrings/azlux-archive-keyring.gpg",
        'echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/azlux-archive-keyring.gpg] http://packages.azlux.fr/debian $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/azlux.list >/dev/null',
        "sudo apt-get update",
        "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ctop"
    ]

    client = get_ssh_client(host, username, password)
    try:
        logger.info(f"Iniciando instalação do Ctop em {host}...")
        for cmd in commands:
            run_ssh_command(client, cmd, timeout=60)
        logger.info("Instalação do Ctop concluída com sucesso.")
        return {"status": "success", "message": "Ctop instalado com sucesso"}
    finally:
        client.close()
