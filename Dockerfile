FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends vim pandoc tesseract-ocr tesseract-ocr-chi-sim && rm -rf /var/lib/apt/lists/*

WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
COPY ./main.py /code/

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80", "--timeout-keep-alive", "150"]