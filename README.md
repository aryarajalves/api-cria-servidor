# API Cria Servidor e Extensão Chrome

Este projeto consiste em uma automação para facilitar a criação e configuração de servidores (VPS), gerenciando stacks via Portainer e DNS via Cloudflare, auxiliado por uma extensão do Google Chrome.

## 🚀 Funcionalidades

*   **API Python**: Gerencia a comunicação com a VPS, instalação de stacks docker (como Portainer, Traefik, Redis, Minio, Baserow, Chatwoot, etc.) e configuração de DNS.
*   **Extensão Chrome**: Interface facilitadora para capturar dados e interagir com a API localmente ou remotamente.
*   **Integração Cloudflare**: Automação de apontamentos DNS para os serviços instalados.

## 🛠️ Pré-requisitos

Para que a automação funcione corretamente, você precisará de:

1.  **Python 3.x** instalado.
2.  **Conta na Cloudflare** e uma **API Key** com permissões para editar zonas DNS.
3.  Um domínio gerenciado pela Cloudflare.
4.  Acesso a um servidor VPS (IP e senha root/chave SSH).

## 🔑 Configuração da Cloudflare API Key

O sistema necessita de uma chave de API da Cloudflare para gerenciar os subdomínios dos serviços instalados.

1.  Acesse o painel da Cloudflare.
2.  Vá em **My Profile** > **API Tokens**.
3.  Crie um token com permissão de **Edit Zone DNS**.
4.  Essa chave deve ser configurada nas variáveis de ambiente ou passada conforme solicitado pela aplicação.

## 📦 Como Usar

### 1. API / Back-end

Instale as dependências:

```bash
pip install -r requirements.txt
```

Execute o servidor:

```bash
python app/main.py
# ou use o script facilitador se houver
```

### 2. Extensão do Chrome

1.  Abra o Chrome e vá para `chrome://extensions/`.
2.  Ative o "Modo do desenvolvedor" (Developer mode) no canto superior direito.
3.  Clique em "Carregar sem compactação" (Load unpacked).
4.  Selecione a pasta `chrome_extension` deste repositório.
5.  A extensão estará pronta para uso. Use-a para interagir com a API e configurar seus servidores.

## 📂 Estrutura do Projeto

*   `app/`: Código fonte da API e scripts de automação.
    *   `stacks/`: Definições em YAML das stacks Docker (Portainer, Traefik, etc.).
*   `chrome_extension/`: Código fonte da extensão (manifest.json, scripts e estilos).

## 📝 Notas Adicionais

*   Certifique-se de que as portas necessárias na VPS não estejam bloqueadas por firewall.
*   A extensão se comunica com a API, portanto o servidor Python deve estar rodando para receber os comandos.
