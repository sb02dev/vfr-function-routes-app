"""Script to run the main server"""
from api import app

print(app.title)

if __name__=="__main__":
    import uvicorn
    uvicorn.run("vfr_function_routes_server:app",
                host="0.0.0.0", port=8000,
                log_level="debug",
                reload=True,
                reload_includes="**/*.{py,htm*,js}"
               )
