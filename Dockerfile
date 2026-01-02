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

# Comando padrão para iniciar a aplicação
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]