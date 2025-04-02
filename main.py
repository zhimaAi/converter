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

app = FastAPI()

logging.basicConfig(level=logging.INFO)

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
    # 设置超时时间（秒）
    timeout = 180  # OCR 需要更长的处理时间
    
    try:
        # 创建输出目录
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)
        
        # 获取输入文件的基本名称（不含扩展名）
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        
        cmd = [
            "docling",
            input_path,
            "--force-ocr",
            "--to", "html",
            "--pdf-backend", "pypdfium2",
            "--ocr-engine", "tesseract",
            "--ocr-lang=chi_sim",
            "--output", output_dir,
            "--verbose",
        ]
        
        logging.info(f"执行命令: {' '.join(cmd)}")
        
        # 启动进程
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        async def read_stream(stream):
            try:
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    text = line.decode().strip()
                    if text:
                        # 根据日志内容判断日志级别
                        if text.startswith(("INFO:", "INFO：")):
                            logging.info(f"Docling: {text}")
                        elif text.startswith(("WARNING:", "WARNING：", "WARN:", "WARN：")):
                            logging.warning(f"Docling: {text}")
                        elif text.startswith(("ERROR:", "ERROR：")):
                            logging.error(f"Docling: {text}")
                        elif text.startswith(("DEBUG:", "DEBUG：")):
                            logging.debug(f"Docling: {text}")
                        else:
                            logging.info(f"Docling: {text}")
            except Exception as e:
                logging.error(f"读取输出流错误: {e}")
        
        try:
            # 创建两个任务来并行读取 stdout 和 stderr
            stdout_task = asyncio.create_task(read_stream(process.stdout))
            stderr_task = asyncio.create_task(read_stream(process.stderr))
            
            # 等待进程完成，设置超时
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                raise Exception(f"Docling转换超时，超过了{timeout}秒的限制")
            
            # 等待输出流读取完成
            await stdout_task
            await stderr_task
            
            if process.returncode != 0:
                raise Exception(f"Docling转换失败，返回码: {process.returncode}")
            
            # docling 会在输出目录生成 {base_name}.html 文件
            expected_output = os.path.join(output_dir, f"{base_name}.html")
            if not os.path.isfile(expected_output):
                raise Exception("Docling转换失败: 输出文件未生成")
            
            # 如果输出文件不在预期位置，移动到正确位置
            if expected_output != output_path:
                os.rename(expected_output, output_path)
                logging.info(f"已将输出文件从 {expected_output} 移动到 {output_path}")
                
        except asyncio.TimeoutError:
            if process.returncode is None:
                process.kill()
            raise Exception(f"Docling转换超时，超过了{timeout}秒的限制")
        finally:
            # 确保子进程被终止
            if process.returncode is None:
                process.kill()
            
    except Exception as e:
        logging.error(f"Docling转换出错: {e}")
        raise

async def delete_files_async(file_paths, delay):
    await asyncio.sleep(delay)
    for path in file_paths:
        if os.path.exists(path):
            os.remove(path)
