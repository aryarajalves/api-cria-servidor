

def check_ctop_installed(host, username, password):
    """
    Verifica se o Ctop está instalado no servidor remoto.
    Retorna True se instalado, False caso contrário.
    """
    client = get_ssh_client(host, username, password)
    try:
        try:
            run_ssh_command(client, "which ctop")
            return True
        except Exception:
            return False
    finally:
        client.close()


def install_ctop(host, username, password):
    """
    Instala o Ctop (container monitoring tool) no servidor remoto via SSH.
    """
    commands = [
        "sudo apt-get install -y ca-certificates curl gnupg lsb-release",
        "curl -fsSL https://azlux.fr/repo.gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/azlux-archive-keyring.gpg",
        'echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/azlux-archive-keyring.gpg] http://packages.azlux.fr/debian $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/azlux.list >/dev/null',
        "sudo apt-get update",
        "sudo apt-get install -y docker-ctop"
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
