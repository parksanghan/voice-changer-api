openSocket = () => {
    socket = new WebSocket("ws://127.0.0.1:9997/");

    // Assume you have 10 canvas elements with IDs msg1, msg2, ..., msg10
    let canvases = [];
    for (let i = 1; i <= 10; i++) {
        canvases.push(document.getElementById("msg" + i));
    }

    let ctxList = canvases.map(canvas => canvas.getContext("2d"));

    socket.addEventListener('open', (e) => {
        document.getElementById("status").innerHTML = "Opened";
    });

    socket.addEventListener('message', (e) => {
        // Assuming the received data is an image
        let image = new Image();
        image.src = URL.createObjectURL(e.data);

        image.addEventListener("load", (e) => {
            for (let i = 0; i < canvases.length; i++) {
                ctxList[i].drawImage(image, 0, 0, canvases[i].width, canvases[i].height);
            }
        });
    });
}
