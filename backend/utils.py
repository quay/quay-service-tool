from flask import request

def is_valid_severity(severity):
    return severity in ["default", "success", "info", "danger", "warning"]

def authenticate_email(email):
    #Make call to USer
    if not email:
        return
    with request.db.cursor() as cur:
        cur.execute("SELECT * from messages")
    return
