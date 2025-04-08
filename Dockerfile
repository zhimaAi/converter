FROM python:3.12-slim-bookworm

# 安装基础包
RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    pandoc \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

# 设置环境变量
ENV HF_ENDPOINT=https://hf-mirror.com
ENV HF_HOME=/root/.cache/huggingface

# 复制依赖文件
COPY ./requirements.txt /code/requirements.txt

# 安装 Python 依赖
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# 复制测试 PDF 并执行转换来预下载模型
COPY ./test.pdf /code/test.pdf
RUN python -c "from docling.document_converter import DocumentConverter; \
    from docling.datamodel.base_models import InputFormat; \
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions; \
    from docling.document_converter import PdfFormatOption; \
    pipeline_options = PdfPipelineOptions(); \
    pipeline_options.force_backend_text = True; \
    pipeline_options.do_ocr = True; \
    pipeline_options.do_table_structure = False; \
    pipeline_options.do_picture_description = False; \
    ocr_options = TesseractCliOcrOptions(force_full_page_ocr=True, lang=['chi_sim']); \
    pipeline_options.ocr_options = ocr_options; \
    format_option = PdfFormatOption(pipeline_options=pipeline_options); \
    converter = DocumentConverter(format_options={InputFormat.PDF: format_option}); \
    doc = converter.convert('test.pdf').document; \
    doc.export_to_html()" && \
    rm test.pdf

# 复制应用代码
COPY ./main.py /code/

# 设置离线模式（构建完成后）
ENV DOCLING_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80", "--timeout-keep-alive", "60"]