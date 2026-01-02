from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from app.installer import install_docker, init_swarm, create_network, install_traefik, install_portainer, check_docker_installed, check_swarm_active, check_network_exists, check_stack_exists, install_redis, install_postgres, install_rabbitmq, install_minio, install_baserow, install_n8n, install_chatwoot
from app.dns_manager import list_zones, create_dns_record, list_dns_records, delete_dns_record, update_dns_record
import logging
import os

# Configura logging
logging.basicConfig(level=logging.INFO)

# Inicializa FastAPI
app = FastAPI()

class DNSRecordDeleteRequest(BaseModel):
    api_token: str
    zone_id: str
    record_id: str

class DNSRecordUpdateRequest(BaseModel):
    api_token: str
    zone_id: str
    record_id: str
    name: str
    content: str
    proxied: bool = True

# ... existing endpoints ...

@app.post("/cloudflare/delete")
def delete_cf_record(req: DNSRecordDeleteRequest):
    try:
        result = delete_dns_record(req.api_token, req.zone_id, req.record_id)
        return {"message": "Registro deletado com sucesso!", "details": result}
    except Exception as e:
        logging.error(f"Error deleting record: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/cloudflare/update")
def update_cf_record(req: DNSRecordUpdateRequest):
    try:
        result = update_dns_record(
            req.api_token, 
            req.zone_id, 
            req.record_id, 
            req.name, 
            req.content, 
            req.proxied
        )
        return {"message": "Registro atualizado com sucesso!", "details": result}
    except Exception as e:
        logging.error(f"Error updating record: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# Logging já configurado no início do arquivo (linha 12)

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

class CloudflareAuth(BaseModel):
    api_token: str

class DNSRecordRequest(BaseModel):
    api_token: str
    zone_id: str
    name: str # Subdomain or @
    content: str # IP
    proxied: bool = True

@app.post("/cloudflare/zones")
def get_cf_zones(auth: CloudflareAuth):
    try:
        zones = list_zones(auth.api_token)
        return {"zones": zones}
    except Exception as e:
        # Log error for debugging
        logging.error(f"Error fetching zones: {e}")
        # Return 400 so frontend catches it
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/cloudflare/create")
def create_cf_record(req: DNSRecordRequest):
    try:
        result = create_dns_record(
            req.api_token, 
            req.zone_id, 
            req.name, 
            req.content, 
            req.proxied
        )
        return {"message": "Registro DNS criado com sucesso!", "details": result}
    except Exception as e:
        logging.error(f"Error creating record: {e}")
        raise HTTPException(status_code=400, detail=str(e))

class DNSListRequest(BaseModel):
    api_token: str
    zone_id: str
    ip_filter: Optional[str] = None

@app.post("/cloudflare/records")
def list_cf_records(req: DNSListRequest):
    try:
        records = list_dns_records(req.api_token, req.zone_id, req.ip_filter)
        return {"records": records}
    except Exception as e:
        logging.error(f"Error listing records: {e}")
        raise HTTPException(status_code=400, detail=str(e))

class ServerCredentials(BaseModel):
    host: str
    username: str
    password: str

class NetworkCreateRequest(ServerCredentials):
    network_name: str = "network_swarm_public"
    overwrite: bool = False

@app.get("/")
def read_root():
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.post("/verify-connection")
def verify_connection(credentials: ServerCredentials):
    """
    Verifica APENAS se é possível conectar via SSH (Login).
    Rápido: ~1-3 segundos.
    """
    import time
    start_time = time.time()
    
    logging.info("="*60)
    logging.info(f"[ENDPOINT] /verify-connection recebido")
    logging.info(f"[ENDPOINT] Host: {credentials.host}")
    logging.info(f"[ENDPOINT] Username: {credentials.username}")
    logging.info(f"[ENDPOINT] Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    from app.installer import verify_ssh_connection
    
    try:
        logging.info(f"[ENDPOINT] Chamando verify_ssh_connection...")
        result = verify_ssh_connection(credentials.host, credentials.username, credentials.password)
        
        elapsed = time.time() - start_time
        
        if result:
            logging.info(f"[ENDPOINT] ✓ Conexão bem-sucedida em {elapsed:.2f}s")
            return {"message": "Conectado com sucesso!"}
        else:
            logging.error(f"[ENDPOINT] ✗ Conexão falhou em {elapsed:.2f}s")
            raise HTTPException(status_code=401, detail="Falha na autenticação ou host inacessível")
            
    except HTTPException:
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logging.error(f"[ENDPOINT] ✗ Exceção após {elapsed:.2f}s: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@app.post("/system-status")
def system_status(credentials: ServerCredentials):
    """
    Verifica o estado completo do sistema (Docker, Swarm, Apps).
    Pesado: ~5-15 segundos.
    """
    logging.info(f"Fetching full system status for: {credentials.host}")
    from app.installer import get_full_system_status
    
    status_data = get_full_system_status(credentials.host, credentials.username, credentials.password)
    
    return {
        "system_status": {
            "docker": status_data["docker"],
            "swarm": status_data["swarm"],
            "network": status_data["network"],
            "ctop": status_data["ctop"]
        },
        "detected_stacks": status_data["active_stacks"]
    }

# Dicionário para armazenar o status das instalações
install_status = {}

@app.get("/install-status/{service}")
def get_install_status(service: str):
    """
    Retorna o status da instalação de um serviço.
    """
    return install_status.get(service, {"status": "unknown", "message": "Serviço não encontrado"})

def run_install_docker_task(host, username, password):
    install_status['docker'] = {'status': 'running', 'message': 'Instalando Docker...'}
    try:
        from app.installer import install_docker, update_docker_version_config
        
        # 1. Instala o Docker
        result = install_docker(host, username, password)
        
        # 2. Atualiza a configuração da versão da API (Automático)
        install_status['docker'] = {'status': 'running', 'message': 'Atualizando configuração do Docker...'}
        update_docker_version_config(host, username, password)
        
        install_status['docker'] = {'status': 'success', 'message': 'Docker instalado e configurado com sucesso!'}
    except Exception as e:
        logger.error(f"Erro na task de instalação do Docker: {e}")
        install_status['docker'] = {'status': 'error', 'message': str(e)}

@app.post("/install-docker")
def trigger_docker_install(credentials: ServerCredentials, background_tasks: BackgroundTasks):
    """
    Inicia o processo de instalação do Docker em um servidor remoto.
    """
    try:
        # Verifica se o Docker já está instalado
        existing_version = check_docker_installed(credentials.host, credentials.username, credentials.password)
        if existing_version:
             return {"message": f"Docker já está instalado com sucesso. Versão: {existing_version}"}

        # Inicia a task com o wrapper para atualizar o status
        background_tasks.add_task(run_install_docker_task, credentials.host, credentials.username, credentials.password)
        return {"message": f"Instalação do Docker iniciada em {credentials.host}"}
    except Exception as e:
        logger.error(f"Falha ao iniciar a instalação: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def run_upgrade_docker_task(host, username, password):
    install_status['docker-upgrade'] = {'status': 'running', 'message': 'Atualizando Docker...'}
    try:
        from app.installer import upgrade_docker_engine
        result = upgrade_docker_engine(host, username, password)
        install_status['docker-upgrade'] = {'status': 'success', 'message': result.get('message', 'Docker atualizado com sucesso!')}
    except Exception as e:
        logger.error(f"Erro na task de atualização do Docker: {e}")
        install_status['docker-upgrade'] = {'status': 'error', 'message': str(e)}

def run_init_swarm_task(host, username, password, advertise_addr):
    install_status['swarm'] = {'status': 'running', 'message': 'Inicializando Swarm...'}
    try:
        from app.installer import init_swarm
        result = init_swarm(host, username, password, advertise_addr)
        install_status['swarm'] = {'status': 'success', 'message': result.get('message', 'Swarm inicializado com sucesso!')}
    except Exception as e:
        logger.error(f"Erro na task de Swarm: {e}")
        install_status['swarm'] = {'status': 'error', 'message': str(e)}

def run_create_network_task(host, username, password, network_name):
    install_status['network'] = {'status': 'running', 'message': 'Criando rede...'}
    try:
        from app.installer import create_network
        result = create_network(host, username, password, network_name)
        install_status['network'] = {'status': 'success', 'message': result.get('message', 'Rede criada com sucesso!')}
    except Exception as e:
        logger.error(f"Erro na task de Rede: {e}")
        install_status['network'] = {'status': 'error', 'message': str(e)}

def run_install_ctop_task(host, username, password):
    install_status['ctop'] = {'status': 'running', 'message': 'Instalando Ctop...'}
    try:
        from app.installer import install_ctop
        result = install_ctop(host, username, password)
        install_status['ctop'] = {'status': 'success', 'message': result.get('message', 'Ctop instalado com sucesso!')}
    except Exception as e:
        logger.error(f"Erro na task de Ctop: {e}")
        install_status['ctop'] = {'status': 'error', 'message': str(e)}


@app.post("/upgrade-docker")
def trigger_docker_upgrade(credentials: ServerCredentials, background_tasks: BackgroundTasks):
    """
    Inicia o processo de atualização do Docker Engine em um servidor remoto.
    """
    try:
        background_tasks.add_task(run_upgrade_docker_task, credentials.host, credentials.username, credentials.password)
        return {"message": f"Atualização do Docker iniciada em {credentials.host}"}
    except Exception as e:
        logger.error(f"Falha ao iniciar a atualização: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/init-swarm")
def trigger_swarm_init(credentials: ServerCredentials, background_tasks: BackgroundTasks):
    """
    Inicializa o Docker Swarm em um servidor remoto.
    """
    try:
        # Verifica se o Swarm já está ativo
        if check_swarm_active(credentials.host, credentials.username, credentials.password):
             return {"message": f"Swarm já está ativo e inicializado em {credentials.host}"}

        # Usa o próprio IP do host como advertise_addr
        background_tasks.add_task(run_init_swarm_task, credentials.host, credentials.username, credentials.password, credentials.host)
        return {"message": f"Inicialização do Swarm iniciada para {credentials.host}"}
    except Exception as e:
        logger.error(f"Falha ao inicializar o swarm: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create-network")
def trigger_create_network(request: NetworkCreateRequest, background_tasks: BackgroundTasks):
    """
    Cria uma rede overlay Docker em um servidor remoto.
    """
    try:
        # Verifica se a rede já existe
        if check_network_exists(request.host, request.username, request.password, request.network_name) and not request.overwrite:
             return {"message": f"A rede '{request.network_name}' já existe em {request.host}. Use 'overwrite': true para forçar."}

        background_tasks.add_task(run_create_network_task, request.host, request.username, request.password, request.network_name)
        return {"message": f"Criação da rede iniciada para {request.network_name} em {request.host}"}
    except Exception as e:
        logger.error(f"Falha ao criar a rede: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/install-ctop")
def trigger_ctop_install(credentials: ServerCredentials, background_tasks: BackgroundTasks):
    """
    Instala o Ctop em um servidor remoto.
    """
    try:
        background_tasks.add_task(run_install_ctop_task, credentials.host, credentials.username, credentials.password)
        return {"message": f"Instalação do Ctop iniciada em {credentials.host}"}
    except Exception as e:
        logger.error(f"Falha ao iniciar instalação do Ctop: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/atualiza_versao_docker")
def trigger_update_docker_version(credentials: ServerCredentials, background_tasks: BackgroundTasks):
    """
    Aplica a correção de versão da API do Docker (DOCKER_MIN_API_VERSION=1.24) para compatibilidade.
    """
    try:
        # Verifica se o Docker está instalado
        existing_version = check_docker_installed(credentials.host, credentials.username, credentials.password)
        if not existing_version:
             return {"message": f"Docker não está instalado em {credentials.host}. Instale o Docker primeiro."}

        from app.installer import update_docker_version_config
        background_tasks.add_task(update_docker_version_config, credentials.host, credentials.username, credentials.password)
        return {"message": f"Atualização da configuração do Docker iniciada em {credentials.host}"}
    except Exception as e:
        logger.error(f"Falha ao atualizar configuração do Docker: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def run_generic_install_task(service_key, install_func, *args, **kwargs):
    install_status[service_key] = {'status': 'running', 'message': f'Instalando {service_key}...'}
    try:
        result = install_func(*args, **kwargs)
        msg = f'{service_key.capitalize()} instalado com sucesso!'
        if isinstance(result, dict) and 'message' in result:
            msg = result['message']
        install_status[service_key] = {'status': 'success', 'message': msg}
    except Exception as e:
        logger.error(f"Erro na task de {service_key}: {e}")
        install_status[service_key] = {'status': 'error', 'message': str(e)}

class RedisInstallRequest(ServerCredentials):
    portainer_api_key: Optional[str] = None

@app.post("/install-redis")
def trigger_install_redis(request: RedisInstallRequest, background_tasks: BackgroundTasks):
    """
    Faz o deploy da stack do Redis.
    """
    try:
        # Verifica se a stack já existe
        if check_stack_exists(request.host, request.username, request.password, "redis"):
             return {"message": f"A stack 'redis' já está rodando em {request.host}"}

        if check_stack_exists(request.host, request.username, request.password, "redis"):
             return {"message": f"A stack 'redis' já está rodando em {request.host}"}

        # Revertendo para instalação padrão via SSH (docker stack deploy)
        # O usuário preferiu o método antigo devido a instabilidades com a API do Portainer
        from app.installer import install_redis
        background_tasks.add_task(run_generic_install_task, 'redis', install_redis, request.host, request.username, request.password)
        return {"message": f"Instalação do Redis via SSH iniciada em {request.host}"}
            
    except Exception as e:
        logger.error(f"Falha ao instalar Redis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class PortainerInstallRequest(ServerCredentials):
    portainer_host: str
    overwrite: bool = False

@app.post("/install-portainer")
def trigger_install_portainer(request: PortainerInstallRequest, background_tasks: BackgroundTasks):
    """
    Faz o deploy da stack do Portainer em um servidor remoto.
    """
    try:
        from app.installer import get_active_stacks, install_portainer
        
        # Verifica se a stack já existe
        active_stacks = get_active_stacks(request.host, request.username, request.password)
        
        if "portainer" in active_stacks and not request.overwrite:
             return {
                 "message": f"A stack 'portainer' já está rodando em {request.host}. Use 'overwrite': true para forçar a reinstalação.",
                 "detected_stacks": active_stacks
             }

        background_tasks.add_task(run_generic_install_task, 'portainer', install_portainer, request.host, request.username, request.password, request.portainer_host)
        return {"message": f"Instalação do Portainer iniciada em {request.host}"}
    except Exception as e:
        logger.error(f"Falha ao instalar o Portainer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class TraefikInstallRequest(ServerCredentials):
    email: str
    overwrite: bool = False

@app.post("/install-traefik")
def trigger_install_traefik(request: TraefikInstallRequest, background_tasks: BackgroundTasks):
    """
    Faz o deploy da stack do Traefik em um servidor remoto.
    """
    try:
        # Verifica se a stack já existe
        if check_stack_exists(request.host, request.username, request.password, "traefik") and not request.overwrite:
             return {"message": f"A stack 'traefik' já está rodando em {request.host}. Use 'overwrite': true para forçar."}

        background_tasks.add_task(run_generic_install_task, 'traefik', install_traefik, request.host, request.username, request.password, request.email)
        return {"message": f"Instalação do Traefik iniciada em {request.host}"}
    except Exception as e:
        logger.error(f"Falha ao instalar o Traefik: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class PostgresInstallRequest(ServerCredentials):
    postgres_password: str
    overwrite: bool = False

@app.post("/install-postgres")
def trigger_install_postgres(request: PostgresInstallRequest, background_tasks: BackgroundTasks):
    """
    Faz o deploy da stack do Postgres em um servidor remoto.
    """
    try:
        # Verifica se a stack já existe
        if check_stack_exists(request.host, request.username, request.password, "postgres") and not request.overwrite:
             return {"message": f"A stack 'postgres' já está rodando em {request.host}. Use 'overwrite': true para forçar."}

        from app.installer import install_postgres
        background_tasks.add_task(run_generic_install_task, 'postgres', install_postgres, request.host, request.username, request.password, request.postgres_password)
        return {"message": f"Instalação do Postgres iniciada em {request.host}"}
    except Exception as e:
        logger.error(f"Falha ao instalar Postgres: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class RabbitMQInstallRequest(ServerCredentials):
    rabbit_user: str
    rabbit_password: str
    rabbit_base_url: str
    overwrite: bool = False

@app.post("/install-rabbitmq")
def trigger_install_rabbitmq(request: RabbitMQInstallRequest, background_tasks: BackgroundTasks):
    """
    Faz o deploy da stack do RabbitMQ em um servidor remoto.
    """
    try:
        # Verifica se a stack já existe
        if check_stack_exists(request.host, request.username, request.password, "rabbitmq") and not request.overwrite:
             return {"message": f"A stack 'rabbitmq' já está rodando em {request.host}. Use 'overwrite': true para forçar."}

        from app.installer import install_rabbitmq
        background_tasks.add_task(run_generic_install_task, 'rabbitmq', install_rabbitmq, request.host, request.username, request.password, request.rabbit_user, request.rabbit_password, request.rabbit_base_url)
        return {"message": f"Instalação do RabbitMQ iniciada em {request.host}"}
    except Exception as e:
        logger.error(f"Falha ao instalar RabbitMQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class MinioInstallRequest(ServerCredentials):
    minio_user: str
    minio_password: str
    minio_base_url_private: str
    minio_base_url_public: str
    overwrite: bool = False

@app.post("/install-minio")
def trigger_install_minio(request: MinioInstallRequest, background_tasks: BackgroundTasks):
    """
    Faz o deploy da stack do Minio em um servidor remoto.
    """
    try:
        # Verifica se a stack já existe
        if check_stack_exists(request.host, request.username, request.password, "minio") and not request.overwrite:
             return {"message": f"A stack 'minio' já está rodando em {request.host}. Use 'overwrite': true para forçar."}

        from app.installer import install_minio
        background_tasks.add_task(run_generic_install_task, 'minio', install_minio, request.host, request.username, request.password, request.minio_user, request.minio_password, request.minio_base_url_private, request.minio_base_url_public)
        return {"message": f"Instalação do Minio iniciada em {request.host}"}
    except Exception as e:
        logger.error(f"Falha ao instalar Minio: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class BaserowInstallRequest(ServerCredentials):
    baserow_base_url: str
    postgres_password: str
    overwrite: bool = False

@app.post("/install-baserow")
def trigger_install_baserow(request: BaserowInstallRequest, background_tasks: BackgroundTasks):
    """
    Faz o deploy da stack do Baserow em um servidor remoto.
    """
    try:
        # Verifica se a stack já existe
        if check_stack_exists(request.host, request.username, request.password, "baserow") and not request.overwrite:
             return {"message": f"A stack 'baserow' já está rodando em {request.host}. Use 'overwrite': true para forçar."}

        from app.installer import install_baserow
        background_tasks.add_task(run_generic_install_task, 'baserow', install_baserow, request.host, request.username, request.password, request.baserow_base_url, request.postgres_password)
        return {"message": f"Instalação do Baserow iniciada em {request.host}"}
    except Exception as e:
        logger.error(f"Falha ao instalar Baserow: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ChatwootInstallRequest(ServerCredentials):
    postgres_password: str
    minio_user: str
    minio_password: str
    minio_base_url_public: str
    chatwoot_base_url: str
    overwrite: bool = False

@app.post("/install-chatwoot")
def trigger_install_chatwoot(request: ChatwootInstallRequest, background_tasks: BackgroundTasks):
    """
    Faz o deploy das stacks do Chatwoot (Admin e Sidekiq) em um servidor remoto.
    """
    try:
        # Verifica se a stack já existe
        if check_stack_exists(request.host, request.username, request.password, "chatwoot_admin") and not request.overwrite:
             return {"message": f"A stack 'chatwoot_admin' já está rodando em {request.host}. Use 'overwrite': true para forçar."}

        from app.installer import install_chatwoot
        background_tasks.add_task(run_generic_install_task, 'chatwoot', install_chatwoot, request.host, request.username, request.password, request.postgres_password, request.minio_user, request.minio_password, request.minio_base_url_public, request.chatwoot_base_url)
        return {"message": f"Instalação do Chatwoot iniciada em {request.host}"}
    except Exception as e:
        logger.error(f"Falha ao instalar Chatwoot: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class EnvUpdate(BaseModel):
    host: str
    username: str
    password: str
    stack_name: str
    env_vars: dict

@app.post("/get-stack-env/{stack_name}")
def get_stack_env(stack_name: str, credentials: ServerCredentials):
    """
    Obtém as variáveis de ambiente de uma stack.
    """
    from app.installer import get_stack_env_vars
    try:
        env_vars = get_stack_env_vars(credentials.host, credentials.username, credentials.password, stack_name)
        return {"env_vars": env_vars}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update-stack-env")
def update_stack_env(data: EnvUpdate):
    """
    Atualiza as variáveis de ambiente de uma stack.
    """
    from app.installer import update_stack_env_vars
    try:
        result = update_stack_env_vars(data.host, data.username, data.password, data.stack_name, data.env_vars)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class RestartStackRequest(ServerCredentials):
    stack_name: str

@app.post("/restart-stack")
def trigger_restart_stack(request: RestartStackRequest, background_tasks: BackgroundTasks):
    """
    Reinicia todos os serviços de uma stack específica.
    """
    try:
        from app.installer import restart_stack_services
        background_tasks.add_task(restart_stack_services, request.host, request.username, request.password, request.stack_name)
        return {"message": f"Reinício da stack '{request.stack_name}' iniciado em {request.host}"}
    except Exception as e:
        logger.error(f"Falha ao reiniciar stack: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class N8NInstallRequest(ServerCredentials):
    postgres_password: str
    n8n_host: str
    n8n_webhook_url: str
    overwrite: bool = False

@app.post("/install-n8n")
def trigger_install_n8n(request: N8NInstallRequest, background_tasks: BackgroundTasks):
    """
    Faz o deploy das stacks do N8N (Editor, Webhook, Worker) em um servidor remoto.
    """
    try:
        # Verifica se a stack já existe
        if check_stack_exists(request.host, request.username, request.password, "n8n_editor") and not request.overwrite:
             return {"message": f"A stack 'n8n_editor' já está rodando em {request.host}. Use 'overwrite': true para forçar."}

        from app.installer import install_n8n
        background_tasks.add_task(run_generic_install_task, 'n8n', install_n8n, request.host, request.username, request.password, request.postgres_password, request.n8n_host, request.n8n_webhook_url)
        return {"message": f"Instalação do N8N iniciada em {request.host}"}
    except Exception as e:
        logger.error(f"Falha ao instalar N8N: {e}")
        raise HTTPException(status_code=500, detail=str(e))

