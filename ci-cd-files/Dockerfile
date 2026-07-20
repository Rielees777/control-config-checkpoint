FROM registry.sovcombank.group/devnetops-dc/uss-rusca-db:8.0

WORKDIR /app
COPY ./ /app

RUN pip install -r requirements.txt \
    --trusted-host nexus.sovcombank.group \
    --index-url "https://nexus.sovcombank.group/repository/pypi-proxy/simple"
    
RUN chmod -R 777 /app
USER nobody

CMD python main.py 
