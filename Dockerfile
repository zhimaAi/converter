FROM python:3.12-bookworm

RUN apt-get update && apt-get install -y texlive-full pandoc fonts-noto-cjk

WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
COPY ./main.py /code/

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
