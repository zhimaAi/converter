from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.responses import FileResponse
from tempfile import mkdtemp, TemporaryDirectory
from pdf2docx import Converter
import asyncio
import pypandoc
import logging
import os

app = FastAPI()

logging.basicConfig(level=logging.INFO)

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "hello, world!"

@app.get("/ping", response_class=PlainTextResponse)
async def pong():
    return "pong"

@app.post("/convert")
async def convert(from_format: str = Form(...), to_format: str = Form(...), file: UploadFile = File(None), content: str = Form(None)):
    if file is None and content is None:
        raise HTTPException(status_code=400, detail="Either a file or content must be provided.")
    
    tmpdir = mkdtemp()
        
    try:
        input_path = os.path.join(tmpdir, f'input.{from_format}')
        intermediate_path = os.path.join(tmpdir, f'intermediate.docx')
        output_path = os.path.join(tmpdir, f'output.{to_format}')

        await save_uploaded_file(file, content, input_path)
        if from_format == "pdf":
            convert_pdf_to_docx(input_path, intermediate_path)
            if to_format == "docx":
                final_path = intermediate_path
            else:
                convert_with_pandoc(intermediate_path, to_format, output_path)
                final_path = output_path
        else:
            convert_with_pandoc(input_path, to_format, output_path)
            final_path = output_path

        response = FileResponse(path=final_path, filename=f'converted.{to_format}', media_type='application/octet-stream')
        asyncio.create_task(delete_files_async([input_path, intermediate_path, output_path], 60))  # Delay in seconds
        return response

    except Exception as e:
        asyncio.create_task(delete_files_async([input_path, intermediate_path, output_path], 0))  # Immediate cleanup
        logging.error(f"Error during conversion: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
async def save_uploaded_file(file, content, path):
    if file:
        content = await file.read()
    elif content:
        content = content.encode()
    
    with open(path, 'wb') as f:
        f.write(content)

def convert_document(from_format, to_format, input_path, output_path):
    if from_format == "pdf" and to_format == "docx":
        convert_pdf_to_docx(input_path, output_path)
    else:
        convert_with_pandoc(input_path, to_format, output_path)

def convert_pdf_to_docx(input_path, output_path):
    cv = Converter(input_path)
    cv.convert(output_path, multi_processing=True) 
    cv.close()

def convert_with_pandoc(input_path, to_format, output_path):
    pdoc_args = []
    if to_format == "html":
        pdoc_args = ["--embed-resources"]
    elif to_format == "pdf":
        pdoc_args = ["--pdf-engine=xelatex", "-V", "mainfont=Noto Sans CJK SC"]
    pypandoc.convert_file(input_path, to_format, outputfile=output_path, extra_args=pdoc_args)

async def delete_files_async(file_paths, delay):
    await asyncio.sleep(delay)
    for path in file_paths:
        if os.path.exists(path):
            os.remove(path)