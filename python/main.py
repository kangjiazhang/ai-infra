import asyncio
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()


async def async_stream_generator():
    for i in range(5):
        print("send:", i)
        yield f"async chunk {i}\n"
        await asyncio.sleep(1)


@app.get("/async-stream")
async def async_stream():
    return StreamingResponse(
        async_stream_generator(),
        media_type="text/event-stream"
    )
