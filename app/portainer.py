import requests
import logging

# Configura o logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_portainer_token(base_url, username, password, verify=True):
    """
    Autentica no Portainer e retorna o token JWT.
    """
    base_url = base_url.rstrip('/')
    url = f"{base_url}/api/auth"
    payload = {
        "Username": username,
        "Password": password
    }
    
    print(f"DEBUG: Tentando autenticar em {url} com usuário {username}")
    try:
        response = requests.post(url, json=payload, verify=verify)
        response.raise_for_status()
        print("DEBUG: Autenticação bem sucedida.")
        return response.json().get("jwt")
    except requests.exceptions.RequestException as e:
        print(f"ERRO: Falha na autenticação do Portainer: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"ERRO: Detalhes da resposta: {e.response.text}")
        raise Exception(f"Falha na autenticação do Portainer: {e}")

def get_first_swarm_endpoint_id(base_url, token=None, api_key=None, verify=True):
    """
    Busca o ID do primeiro endpoint (environment) do tipo Swarm disponível.
    Suporta Token (Bearer) ou API Key (X-API-Key).
    """
    base_url = base_url.rstrip('/')
    url = f"{base_url}/api/endpoints"
    
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    elif token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        raise ValueError("É necessário fornecer token ou api_key.")
    
    print(f"DEBUG: Buscando endpoints em {url}")
    try:
        response = requests.get(url, headers=headers, verify=verify)
        response.raise_for_status()
        endpoints = response.json()
        
        for endpoint in endpoints:
            # Type 1 = Docker (pode ser Swarm ou Standalone), Type 2 = Agent (Swarm)
            # Vamos assumir que queremos o primeiro endpoint ativo
            print(f"DEBUG: Encontrado endpoint: ID={endpoint.get('Id')}, Name={endpoint.get('Name')}, Type={endpoint.get('Type')}, Status={endpoint.get('Status')}")
            if endpoint.get("Status") == 1: # 1 = Up
                return endpoint.get("Id")
        
        raise Exception("Nenhum endpoint ativo encontrado no Portainer.")
    except requests.exceptions.RequestException as e:
        print(f"ERRO: Falha ao listar endpoints do Portainer: {e}")
        raise Exception(f"Falha ao listar endpoints do Portainer: {e}")

def deploy_stack_portainer(base_url, stack_name, stack_content, endpoint_id, token=None, api_key=None, verify=True):
    """
    Faz o deploy de uma stack no Portainer via API.
    Suporta Token (Bearer) ou API Key (X-API-Key).
    """
    base_url = base_url.rstrip('/')
    # Verifica se a stack já existe
    check_url = f"{base_url}/api/stacks"
    
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    elif token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        raise ValueError("É necessário fornecer token ou api_key.")
        
    print(f"DEBUG: Verificando se stack {stack_name} já existe...")
    try:
        response = requests.get(check_url, headers=headers, verify=verify)
        response.raise_for_status()
        stacks = response.json()
        
        for stack in stacks:
            if stack.get("Name") == stack_name:
                print(f"INFO: Stack {stack_name} já existe no Portainer.")
                return {"status": "success", "message": f"Stack {stack_name} já existe no Portainer"}
    except Exception as e:
        print(f"AVISO: Não foi possível verificar se a stack existe: {e}")

    # Cria a stack
    # Type 1 = Swarm Stack
    # Parametros de query
    query_params = {
        "type": 1,
        "method": "string",
        "endpointId": endpoint_id
    }
    
    url = f"{base_url}/api/stacks"
    
    payload = {
        "Name": stack_name,
        "StackFileContent": stack_content,
        "SwarmID": "swarmi-id-placeholder" 
    }
    
    # Precisamos pegar o SwarmID real do endpoint para criar uma Swarm Stack corretamente
    # GET /api/endpoints/{id}/docker/info
    try:
        info_url = f"{base_url}/api/endpoints/{endpoint_id}/docker/info"
        info_response = requests.get(info_url, headers=headers, verify=verify)
        info_response.raise_for_status()
        swarm_id = info_response.json().get("Swarm", {}).get("Cluster", {}).get("ID")
        if swarm_id:
            payload["SwarmID"] = swarm_id
            print(f"DEBUG: Swarm ID encontrado: {swarm_id}")
        else:
            print("AVISO: Swarm ID não encontrado no endpoint.")
    except Exception as e:
        print(f"AVISO: Erro ao buscar Swarm ID: {e}")

    print(f"DEBUG: Tentando criar stack '{stack_name}' no Endpoint ID {endpoint_id}...")
    
    try:
        # allow_redirects=False para detectar se o Portainer está redirecionando (ex: http -> https)
        response = requests.post(url, headers=headers, params=query_params, json=payload, verify=verify, allow_redirects=False)
        
        if response.status_code in [301, 302, 307, 308]:
             print(f"AVISO: Redirect detectado para {response.headers.get('Location')}")
             raise Exception(f"Portainer redirecionou a requisição. Tente usar HTTPS ou a URL correta.")

        response.raise_for_status()
        print(f"INFO: Stack {stack_name} criada com sucesso no Portainer.")
        return {"status": "success", "message": f"Stack {stack_name} criada com sucesso no Portainer"}
    except requests.exceptions.RequestException as e:
        error_msg = response.text if response else str(e)
        print(f"ERRO: Falha ao criar stack no Portainer. Status: {response.status_code if response else 'N/A'}")
        print(f"ERRO: Resposta do Portainer: {error_msg}")
        # Retorna o erro detalhado para aparecer no popup
        raise Exception(f"Status {response.status_code if response else 'N/A'} - {error_msg}")
