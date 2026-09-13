# Pricing in micro-cents (1 cent = 10,000 micro-cents) to avoid floats
PRICING = {
    "api_call": 10000,           # $0.01 per API call
    "input_token": 100,          # $0.0001 per input token
    "cached_input_token": 50,    # $0.00005 per cached token (cheaper)
    "output_token": 400,         # $0.0004 per output token
    "reasoning_token": 400       # Reasoning counts as output (same price)
}