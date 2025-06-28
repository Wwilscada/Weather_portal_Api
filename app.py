from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from flask_cors import CORS
from datetime import datetime, timedelta
import pyodbc
import requests

app = Flask(__name__)
CORS(app)
app.secret_key = "secret"  # Consider moving this to an environment variable

# Configuration
VC_API_KEYS = [
    '6NSHBH2VCR2BPN6WMYRGLL4JX',
    '77EEYBH9HP5EFD3QJ44M7DX39',
    'E9VD8EY5W25NQJ4ATLYE4NB42',
    '7BSCDLVXUSBKW49LU5LNCJQYV',
    'JFSSVCVP2PZV6FL2HRPLMADAT',
    'DSR5VPHEX7JAARV7BET5TST9T',
    '9QE7RYKNFAR488VSFEP7MRZDG',
    'P8VTN4UHMDAMQHTFF9XMLQNMC',
    '2ECCLNJ89FMCU53G6VWLQCU5Q'
]

DB_CONFIG = {
    "server": "172.18.25.38",
    "user": "sa",
    "password": "wwilscada@4444",
    "database": "Weatherforecast"
}

def get_db_connection():
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DB_CONFIG['server']};DATABASE={DB_CONFIG['database']};"
        f"UID={DB_CONFIG['user']};PWD={DB_CONFIG['password']};Trusted_Connection=no;"
    )
    return pyodbc.connect(conn_str)

def convert_wind_direction(degrees):
    try:
        directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
        idx = round(float(degrees) / 45) % 8
        return directions[idx]
    except Exception:
        return 'Unknown'

def fetch_weather_data(lat, lon):
    today = datetime.now().date()
    end_date = today + timedelta(days=4)
    for key in VC_API_KEYS:
        url = (
            f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"
            f"{lat},{lon}/{today}/{end_date}?unitGroup=metric&key={key}"
        )
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            print(f"✅ API key succeeded: {key}")
            return response.json()
        except Exception as e:
            print(f"⚠️ API key failed: {key} - {e}")
    raise Exception("❌ All API keys failed.")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

def get_weather_icon(condition):
    condition = condition.lower()
    if 'sunny' in condition:
        return '01d'
    elif 'partly' in condition or 'cloudy' in condition:
        return '02d'
    elif 'rain' in condition:
        return '09d'
    elif 'storm' in condition or 'thunder' in condition:
        return '11d'
    elif 'snow' in condition:
        return '13d'
    elif 'fog' in condition or 'mist' in condition:
        return '50d'
    else:
        return '03d'


@app.route("/view_data")
def view_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM WeatherData2 ORDER BY Createdon DESC")
    data = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
    conn.close()
    return render_template("view_data.html", weather_data=data, get_weather_icon=get_weather_icon)


@app.route("/get_filter_hierarchy")
def get_filter_hierarchy():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT State, LOCNO, PlantNo
            FROM WeatherData2
            WHERE State IS NOT NULL AND LOCNO IS NOT NULL AND PlantNo IS NOT NULL
        """)
        rows = cursor.fetchall()
        hierarchy = {}
        for state, loc, plant in rows:
            hierarchy.setdefault(state, {}).setdefault(loc, []).append(plant)
        return jsonify(hierarchy)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass
@app.route('/get_hourly_forecast')
def get_hourly_forecast():
    date = request.args.get('date')
    locno = request.args.get('locno')
    plantno = request.args.get('plantno')

    cursor = conn.cursor() # type: ignore
    query = """
        SELECT 
            FORMAT(CAST(ForecastDateTime AS TIME), 'HH:mm') AS Hour,
            Temp,
            Conditions
        FROM WeatherData2
        WHERE CAST(ForecastDateTime AS DATE) = ?
          AND LOCNO = ? AND PLANTNO = ?
        ORDER BY ForecastDateTime
    """
    cursor.execute(query, date, locno, plantno)
    rows = cursor.fetchall()
    cursor.close()

    # Return every 6th hour (6-hour interval)
    result = [{'Hour': r[0], 'Temp': r[1], 'Conditions': r[2]} for i, r in enumerate(rows) if i % 6 == 0]
    return jsonify(result)


@app.route("/get_weather_by_location", methods=['GET'])
def get_weather_by_location():
    locno = request.args.get('locno')
    plantno = request.args.get('plantno')

    if not locno or not plantno:
        return jsonify({'error': 'Missing locno or plantno parameter'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("EXEC dbo.Weather_data @locno=?, @plantno=?", (locno, plantno))

        columns = [column[0].lower() for column in cursor.description]
        rows = []
        for row in cursor.fetchall():
            row_dict = dict(zip(columns, row))
            rows.append({
                "ForecastDate": row_dict.get("forecastdate") or row_dict.get("forecast_date"),
    "Temp": row_dict.get("temp"),
    "TempMin": row_dict.get("tempmin") or row_dict.get("temp_min"),
    "TempMax": row_dict.get("tempmax") or row_dict.get("temp_max"),
    "Conditions": row_dict.get("conditions"),
    "Humidity": row_dict.get("humidity"),
    "Windspeed": row_dict.get("windspeed"),
    "WindGust": row_dict.get("windgust"),
    "WindDir": row_dict.get("winddir"),
    "Precip": row_dict.get("precip")
    })

        return jsonify(rows)

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass

def save_weather_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        print(f"⏳ Running weather update at {datetime.now()}")
        cursor.execute("""
            SELECT DISTINCT State, LOCNO, PlantNo, Latitude, Longitude
            FROM WEC_All_Data_2
            WHERE Latitude IS NOT NULL AND Longitude IS NOT NULL
        """)
        records = cursor.fetchall()
        count = 0

        for state, locno, plantno, lat, lon in records:
            try:
                data = fetch_weather_data(lat, lon)
                for day in data.get("days", []):
                    forecast_date = datetime.strptime(day["datetime"], "%Y-%m-%d")
                    cursor.execute("""
                        INSERT INTO WeatherData2 (
                            State, LOCNO, PlantNo, Latitude, Longitude, WindSpeed, WindGust,
                            WindDir, Conditions, Temp, TempMin, TempMax, Humidity, Precip,
                            Createdon, ForecastDate
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        state, locno, plantno, lat, lon,
                        day.get("windspeed", 0.0),
                        day.get("windgust", 0.0),
                        convert_wind_direction(day.get("winddir", 0)),
                        day.get("conditions", "Unknown"),
                        day.get("temp", 0.0),
                        day.get("tempmin", 0.0),
                        day.get("tempmax", 0.0),
                        day.get("humidity", 0.0),
                        day.get("precip", 0.0),
                        datetime.now(),
                        forecast_date
                    ))
                    count += 1
            except Exception as e:
                print(f"[Error] Skipped {state}-{locno}: {e}")
        conn.commit()
        print(f"✅ Inserted {count} weather records.")
    except Exception as e:
        print(f"[Error] save_weather_data failed: {e}")
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass

import os
DATABASE_URL = os.getenv("postgresql://weather_db_4hts_user:M7duOBKmwg6I3tCPEpgWfdwRH13f9QOv@dpg-d1ft44ali9vc739v24rg-a/weather_db_4hts")


# Schedule daily weather data collection at 10:10 AM
# scheduler = BackgroundScheduler()
# scheduler.add_job(save_weather_data, 'cron', hour=10, minute=10)
# scheduler.start()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8097)
