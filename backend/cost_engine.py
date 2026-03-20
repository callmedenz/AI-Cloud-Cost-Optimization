# Dictionary for my AWS instance prices per hour
INSTANCE_PRICING = {
    "t2.micro": 0.0116,
    "t2.small": 0.023,
    "t3.micro": 0.0104
}

# math function to get cost
def calculate_cost(instance_type, running_hours):
    price = INSTANCE_PRICING.get(instance_type, 0.02)
    return price * running_hours
