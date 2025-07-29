import sys
print("Python path:", sys.path)

try:
    from aiogram import Bot
    print("✅ Aiogram успешно импортирован!")
except Exception as e:
    print(f"❌ Ошибка: {repr(e)}")