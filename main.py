from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.responses import FileResponse
from tempfile import mkdtemp
from pdf2docx import Converter
import asyncio
import pypandoc
import logging
import os, time

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
    if to_format == "pdf":
        raise HTTPException(status_code=400, detail="Conversion to pdf is not supported")
    if file is None and content is None:
        raise HTTPException(status_code=400, detail="Either a file or content must be provided.")
    
    tmpdir = mkdtemp()
        
    try:
        input_path = os.path.join(tmpdir, f'input.{from_format}')
        intermediate_path = os.path.join(tmpdir, f'intermediate.docx')
        output_path = os.path.join(tmpdir, f'output.{to_format}')

        await save_uploaded_file(file, content, input_path)
        if from_format == "pdf":
            await convert_pdf_to_docx(input_path, intermediate_path)
            if to_format == "docx":
                final_path = intermediate_path
            else:
                await convert_with_pandoc(from_format, intermediate_path, to_format, output_path)
                final_path = output_path
        else:
            await convert_with_pandoc(from_format, input_path, to_format, output_path)
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

async def convert_pdf_to_docx(input_path, output_path):
    try:
        cv = Converter(input_path)
        cv.convert(output_path, multi_processing=True)
        cv.close()
    except Exception as e:
        print(f"An error occurred: {e}")
        # Optionally, fall back to single-processing
        cv.convert(output_path, multi_processing=False)
        cv.close()

async def convert_with_pandoc(from_format, input_path, to_format, output_path):
    if from_format == 'txt' and to_format == 'html':
        with open(input_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
        text = ''.join(line.strip() + '  \n' for line in lines)
        output = pypandoc.convert_text(text, 'html', format='markdown')
        with open(output_path, 'w', encoding='utf-8') as file:
            file.write(output)
    else:
        pdoc_args = ["--embed-resources", "--request-header", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"]
        pypandoc.convert_file(input_path, to_format, outputfile=output_path, extra_args=pdoc_args)

async def delete_files_async(file_paths, delay):
    await asyncio.sleep(delay)
    for path in file_paths:
        if os.path.exists(path):
            os.remove(path)
