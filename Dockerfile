# Usa uma imagem oficial leve que já tem Python 3.12 e Node.js 18
FROM nikolaik/python-nodejs:python3.12-nodejs18-slim

# Define o diretório de trabalho
WORKDIR /app

# Copia as dependências do Python primeiro (otimiza o cache do Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código do projeto para dentro do container
COPY . .

# Build do dashboard (React/Vite)
RUN cd dashboard && npm install && npm run build

# Remove arquivos desnecessários do NPM para limpar espaço (opcional)
RUN rm -rf dashboard/node_modules

# O Railway define a variável PORT dinamicamente, vamos expor a 5000 como padrão caso falhe
ENV PORT=5000
EXPOSE $PORT

# Comando para iniciar o servidor (mesmo do main.py)
CMD ["python", "main.py"]
