from .app import app

@app.sio.on('join')
async def handle_join(sid, *args, **kwargs):
    await app.sio.emit('lobby', 'User joined')


async def handle_addjoin(sid, *args, **kwargs):
    await app.sio.emit()