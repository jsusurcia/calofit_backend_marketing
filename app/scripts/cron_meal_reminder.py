import sys
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# Add the root project directory to the path so we can import 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.client import Client
from app.services.email_service import EmailService

def run_meal_reminders():
    """
    Busca clientes cuyo meal_reminder_time coincide con la hora actual (Perú) 
    y les envía el correo electrónico de recordatorio.
    Se espera que este script se ejecute mediante un cron job (ej: cada hora).
    """
    db: Session = SessionLocal()
    try:
        # Obtener la hora actual en Perú
        tz_peru = ZoneInfo('America/Lima')
        now = datetime.now(tz_peru)
        current_hour_minute = now.strftime("%H:%M") # Formato "HH:MM" (ej. "20:00")
        current_hour = now.strftime("%H")

        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Buscando recordatorios para la hora: {current_hour}")

        # Buscar clientes que tienen un recordatorio configurado para la hora actual.
        # Comparamos solo la hora si la base de datos tiene "HH:MM" para ser flexibles con el cron.
        # O podemos buscar coincidencias exactas.
        
        clientes = db.query(Client).filter(Client.meal_reminder_time.isnot(None)).all()
        enviados = 0

        for cliente in clientes:
            if cliente.meal_reminder_time:
                # Comparamos si la hora (ej: "20") coincide con el inicio de meal_reminder_time
                if cliente.meal_reminder_time.startswith(current_hour):
                    print(f"Enviando recordatorio a {cliente.email} (Hora configurada: {cliente.meal_reminder_time})")
                    EmailService.send_meal_reminder_email(
                        email_to=cliente.email, 
                        client_name=cliente.first_name or "Cliente"
                    )
                    enviados += 1
        
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Proceso finalizado. Total correos enviados: {enviados}")

    except Exception as e:
        print(f"Error durante el envío de recordatorios: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_meal_reminders()
