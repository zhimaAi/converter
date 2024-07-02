from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.responses import FileResponse
from tempfile import NamedTemporaryFile
from pdf2docx import Converter
import asyncio
import pypandoc
import os

app = FastAPI()

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "hello, world!"

@app.get("/ping", response_class=PlainTextResponse)
async def pong():
    return "pong"

@app.post("/convert")
async def convert(from_format: str = Form(...), to_format: str = Form(...), file: UploadFile = File(None), content: str = Form(None)):
    temp_file_path = None
    output_file_path = None

    if file is None and content is None:
        raise HTTPException(status_code=400, detail="Either a file or content must be provided.")

    try:
        with NamedTemporaryFile(delete=False, suffix=f'.{from_format}', mode='wb+') as temp_file:
            temp_file_path = temp_file.name

            if file:
                content = await file.read()
            elif content:
                content = content.encode()

            temp_file.write(content)
            temp_file.flush()

        output_file_path = temp_file_path.replace(f'.{from_format}', f'.{to_format}')

        if from_format == "pdf" and to_format == "docx":
            cv = Converter(temp_file_path)
            cv.convert(output_file_path, multi_processing=True) 
            cv.close()    
        else:    
            pdoc_args = []
            if to_format == "html":
                pdoc_args = ["--embed-resources=true"]
            elif to_format == "pdf":
                pdoc_args = ["--pdf-engine=xelatex", "-V", "mainfont=Noto Sans CJK SC", "header-includes=\setlength{\parindent}{0pt}"]
            pypandoc.convert_file(temp_file_path, to_format, outputfile=output_file_path, extra_args=pdoc_args)

        asyncio.create_task(delete_file(temp_file_path, 60))  # Delete after 1 minutes
        asyncio.create_task(delete_file(output_file_path, 60))  # Delete after 1 minutes

        return FileResponse(path=output_file_path, filename=f'converted.{to_format}', media_type='application/octet-stream')

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def delete_file(path: str, delay: int):
    await asyncio.sleep(delay)  # Delay in seconds
    if os.path.exists(path):
        os.remove(path)