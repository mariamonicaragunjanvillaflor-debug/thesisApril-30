from supabase import create_client
import random
import time

# Your Supabase credentials
SUPABASE_URL = "YOUR_SUPABASE_URL"
SUPABASE_KEY = "YOUR_SUPABASE_ANON_KEY"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

while True:

    # Sample sensor values
    temperature_c = random.uniform(30, 90)
    current_a = random.uniform(5, 30)

    # Example AI prediction values
    overload_probability = random.uniform(0, 1)
    hotspot_probability = random.uniform(0, 1)

    # Composite risk calculation
    composite_risk = (
        overload_probability + hotspot_probability
    ) / 2

    # Breaker logic
    breaker_state = "NORMAL"

    if composite_risk > 0.7:
        breaker_state = "WARNING"

    if composite_risk > 0.9:
        breaker_state = "TRIPPED"

    # Insert into Supabase
    data = {
        "temperature_c": temperature_c,
        "current_a": current_a,
        "breaker_state": breaker_state,
        "overload_probability": overload_probability,
        "hotspot_probability": hotspot_probability,
        "composite_risk": composite_risk
    }

    response = (
        supabase
        .table("breaker_readings")
        .insert(data)
        .execute()
    )

    print("Uploaded:", data)

    time.sleep(5)