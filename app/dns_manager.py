import requests
import logging

def list_zones(api_token):
    """
    Lists available zones (domains) for the given Cloudflare API Token.
    """
    url = "https://api.cloudflare.com/client/v4/zones"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("success"):
            error_msg = data.get("errors", [{"message": "Unknown error"}])[0]["message"]
            raise Exception(f"Cloudflare API Error: {error_msg}")
            
        zones = []
        for zone in data.get("result", []):
            zones.append({
                "id": zone["id"],
                "name": zone["name"]
            })
            
        return zones

    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed: {e}")
        raise Exception(f"Falha na conexão com a Cloudflare: {str(e)}")


def create_dns_record(api_token, zone_id, name, content, proxied=True):
    """
    Creates an 'A' record in Cloudflare.
    """
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    # If name is 'app' and zone is 'example.com', final is 'app.example.com'
    # Cloudflare API accepts the full name or subdomain. 
    # Usually better to send just the name (subdomain) or full name. 
    # The API documentation says 'name': 'DNS record name (or @ for the zone apex)'.
    
    payload = {
        "type": "A",
        "name": name,
        "content": content,
        "ttl": 1, # Automatic
        "proxied": proxied
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        data = response.json()
        
        if not data.get("success"):
             # Check if error is "Record already exists"
            errors = data.get("errors", [])
            for err in errors:
                if "record already exists" in err.get("message", "").lower():
                    raise Exception("Este registro DNS já existe.")
            
            error_msg = errors[0]["message"] if errors else "Unknown error"
            raise Exception(f"Cloudflare Error: {error_msg}")
            
        return {
            "success": True,
            "record": data["result"]
        }

    except requests.exceptions.RequestException as e:
         raise Exception(f"Falha na conexão com a Cloudflare: {str(e)}")

def list_dns_records(api_token, zone_id, ip_filter=None):
    """
    Lists 'A' records in a specific zone, optionally filtered by IP content.
    """
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    params = {
        "type": "A",
        "per_page": 100
    }
    if ip_filter:
        params["content"] = ip_filter

    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        
        if not data.get("success"):
            error_msg = data.get("errors", [{"message": "Unknown error"}])[0]["message"]
            raise Exception(f"Cloudflare Error: {error_msg}")
            
        return data.get("result", [])

    except requests.exceptions.RequestException as e:
        raise Exception(f"Falha na conexão com a Cloudflare: {str(e)}")

def delete_dns_record(api_token, zone_id, record_id):
    """
    Deletes a DNS record.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    logger.info(f"[DELETE DNS] Deletando registro")
    logger.info(f"[DELETE DNS] Zone ID: {zone_id}")
    logger.info(f"[DELETE DNS] Record ID: {record_id}")
    logger.info(f"[DELETE DNS] URL: {url}")

    try:
        response = requests.delete(url, headers=headers)
        data = response.json()
        
        logger.info(f"[DELETE DNS] Status HTTP: {response.status_code}")
        logger.info(f"[DELETE DNS] Resposta Cloudflare: {data}")
        
        if not data.get("success"):
            errors = data.get("errors", [{"message": "Unknown error"}])
            error_msg = errors[0].get("message", "Unknown error")
            logger.error(f"[DELETE DNS] Erro na API: {error_msg}")
            logger.error(f"[DELETE DNS] Erros completos: {errors}")
            raise Exception(f"Cloudflare Error: {error_msg}")
            
        logger.info(f"[DELETE DNS] Registro deletado com sucesso!")
        return data.get("result")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"[DELETE DNS] Falha na requisição: {str(e)}")
        raise Exception(f"Falha na conexão com a Cloudflare: {str(e)}")

def update_dns_record(api_token, zone_id, record_id, name, content, proxied=True):
    """
    Updates an existing 'A' DNS record.
    """
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "type": "A",
        "name": name,
        "content": content,
        "proxied": proxied,
        "ttl": 1
    }

    try:
        response = requests.put(url, headers=headers, json=payload)
        data = response.json()
        
        if not data.get("success"):
            error_msg = data.get("errors", [{"message": "Unknown error"}])[0]["message"]
            raise Exception(f"Cloudflare Error: {error_msg}")
            
        return data.get("result")

    except requests.exceptions.RequestException as e:
        raise Exception(f"Falha na conexão com a Cloudflare: {str(e)}")
