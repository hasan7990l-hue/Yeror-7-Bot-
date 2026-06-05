# استخدام نسخة خفيفة من بايثون
FROM python:3.9-slim

# تعيين مجلد العمل داخل الحاوية
WORKDIR /app

# تثبيت المكتبات النظامية الضرورية (خاصة ffmpeg لمعالجة الفيديو)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# نسخ ملف المتطلبات أولاً لتحسين سرعة البناء (Caching)
COPY requirements.txt .

# تثبيت مكتبات بايثون
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع إلى الحاوية
COPY . .

# فتح منفذ خادم الويب رقم 7860 ليتوافق مع السكربت والبيئات السحابية
EXPOSE 7860

# أمر تشغيل البوت
CMD ["python", "main.py"]
