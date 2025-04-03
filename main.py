from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.responses import FileResponse
from tempfile import mkdtemp
from pdf2docx import Converter
import asyncio
import pypandoc
import logging
import os
import subprocess
import sys
import multiprocessing as mp
from pathlib import Path

app = FastAPI()

logging.basicConfig(level=logging.INFO)
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

def init_docling_converter():
    from docling.backend.docling_parse_backend import DoclingParseDocumentBackend
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TesseractCliOcrOptions,
        TesseractOcrOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption
    
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.do_cell_matching = True
    ocr_options = TesseractCliOcrOptions(force_full_page_ocr=True, lang=["chi_sim"])
    pipeline_options.ocr_options = ocr_options
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
            )
        }
    )
    return converter
converter = init_docling_converter()

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "hello, world!"

@app.get("/ping", response_class=PlainTextResponse)
async def pong():
    return "pong"

@app.post("/convert")
async def convert(from_format: str = Form(...), to_format: str = Form(...), file: UploadFile = File(None), content: str = Form(None), use_ocr: bool = Form(False)):
    # print("收到请求 from_format: ", from_format, " to_format: ", to_format , " file: ", file, " content: ", content)
    logging.info(f"收到请求 from_format: {from_format}, to_format: {to_format}, file: {file}, content: {content}, use_ocr: {use_ocr}")

    if to_format == "pdf":
        raise HTTPException(status_code=400, detail="Conversion to pdf is not supported")
    if file is None and content is None:
        raise HTTPException(status_code=400, detail="Either a file or content must be provided.")
    
    tmpdir = mkdtemp()
    input_path = os.path.join(tmpdir, f'input.{from_format}')
    intermediate_path = os.path.join(tmpdir, f'intermediate.docx')
    output_path = os.path.join(tmpdir, f'output.{to_format}')
        
    try:
        await save_uploaded_file(file, content, input_path)
        if from_format == "pdf":
            if use_ocr and to_format == "html":
                # 使用 docling 直接转换
                await convert_pdf_with_docling(input_path, output_path)
                logging.info("Docling OCR转换成功")
                final_path = output_path
            else:
                await convert_pdf_to_docx(input_path, intermediate_path)
                logging.info("PDF转换成功")
                if to_format == "docx":
                    final_path = intermediate_path
                else:
                    await convert_with_pandoc(from_format, intermediate_path, to_format, output_path)
                    logging.info("Pandoc转换成功")
                    final_path = output_path
        else:
            await convert_with_pandoc(from_format, input_path, to_format, output_path)
            logging.info("Pandoc转换成功")
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
    # 设置超时时间（秒）
    timeout = 60
    
    # 使用子进程执行转换，这样可以完全控制进程生命周期
    process = None
    try:
        cmd = [
            sys.executable, 
            "-c", 
            f"""
import sys
from pdf2docx import Converter
import traceback

try:
    cv = Converter('{input_path}')
    cv.convert('{output_path}')
    cv.close()
except Exception as e:
    print(f"转换错误: {{type(e).__name__}}: {{str(e)}}", file=sys.stderr)
    sys.exit(1)
"""
        ]
        
        # 启动进程
        process = subprocess.Popen(
            cmd,
            stdout=None,
            stderr=None,
            text=True
        )
        
        # 使用asyncio在事件循环中等待进程完成，并设置超时
        try:
            loop = asyncio.get_event_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, process.communicate),
                timeout=timeout
            )
            
            # 检查进程返回码
            if process.returncode != 0:
                raise Exception(f"PDF转换失败，返回码: {process.returncode}")
                
        except asyncio.TimeoutError:
            if process.poll() is None:
                process.kill()
            raise Exception(f"PDF转换超时，超过了{timeout}秒的限制")
            
    except Exception as e:
        # 确保进程被终止
        if process and process.poll() is None:
            process.kill()
        logging.error(f"PDF转换出错: {e}")
        raise

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

async def convert_pdf_with_docling(input_path, output_path):
    try:
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            doc = converter.convert(input_path).document
            content = doc.export_to_html()
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except ImportError as e:
            # 如果无法导入docling相关模块，提供错误信息
            logging.error(f"无法导入Docling相关模块: {e}")
            raise HTTPException(status_code=500, detail="服务器未正确配置OCR功能，请尝试不使用OCR选项")
             
    except Exception as e:
        logging.error(f"Docling转换出错: {e}")
        raise

async def delete_files_async(file_paths, delay):
    await asyncio.sleep(delay)
    for path in file_paths:
        if os.path.exists(path):
            os.remove(path)
