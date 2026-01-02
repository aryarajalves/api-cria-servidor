# 1. Usar uma imagem oficial e leve do Python como base
FROM python:3.9-slim

# 2. Definir o diretório de trabalho dentro do contêiner
WORKDIR /app

# 3. Copiar o arquivo de dependências primeiro para aproveitar o cache do Docker
COPY requirements.txt .

# 4. Instalar as dependências listadas no requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiar todo o resto do seu código para o contêiner
COPY . .

# 6. Expor a porta 8000, que é a porta padrão que o Uvicorn usará
EXPOSE 8000

# O comando para iniciar a aplicação (CMD) será especificado no arquivo docker-compose.yml
# para cada serviço individualmente.