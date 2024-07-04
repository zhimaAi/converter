FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-lang-all \
    texlive-xetex \
    pandoc \
    fonts-noto-cjk \
&& rm -rf /var/lib/apt/lists/*

WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
COPY ./main.py /code/

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
