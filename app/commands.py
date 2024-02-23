from app import app

@app.cli.command('DBDump')
def DBDump():
    print('dumpin')
