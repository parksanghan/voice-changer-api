


window.onload = function() {
    console.log('fired');
    if (typeof webkitSpeechRecognition !== 'function') {
        alert('크롬에서만 동작 합니다.');
        return false;
    }
    const recognition = new window.webkitSpeechRecognition();
    const language = 'ko-KR';
    const micBtn = document.querySelector('.mic');
    const delBtn = document.querySelector('.remove');
    const resultWrap = document.querySelector('.result');
    const recognizedTextarea = document.querySelector('.recognized-textarea');
    const recording_state = document.querySelector('#recording-state');
    
    const final_span = document.querySelector('#final_span');
    const interim_span = document.querySelector('#interim_span');

    let isRecognizing = false;
    let ignoreEndProcess = false;
    let finalTranscript = '';

    recognition.continuous = true;
    recognition.interimResults = false; 
    recognition.onend = null
    //true : recognition이 result의 중간중간을 보고한다

    /**
     * 음성 인식 시작 처리
     */
    recognition.onstart = function (event) {
        console.log('onstart', event);
        isRecognizing = true;
        recording_state.className = 'on';
    };

    /**
     * 음성 인식 종료 처리
     */
    // recognition.onend = function () {
    //     console.log('onend', arguments);
    //     isRecognizing = false;

    //     if (ignoreEndProcess) {
    //         return false;
    //     }

    //     // Do end process
    //     recording_state.className = 'off';
    //     console.log('off')
    //     if (!finalTranscript) {
    //     console.log('empty finalTranscript');
    //     return false;
    //     }
    // };

    /**
     * 음성 인식 결과 처리
     * 밑의 코드는 SpeechRecognition 객체의 onresult Property인 이벤트 핸들러를 설정하는 것임.
     * API로부터 성공적으로 result를 받았을 때 밑에서 정의한 SpeechRecognition 객체의 onresult 이벤트가 핸들러가 호출됨.
     */
    recognition.onresult = function (event) {
        console.log('onresult', event);

        let finalTranscript = '';
        let interimTranscript = '';
        if (typeof event.results === 'undefined') {
            recognition.onend = null;
            recognition.stop();
            return;
        }

        for (let i = event.resultIndex; i < event.results.length; ++i) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                finalTranscript += transcript;
            } else {
                interimTranscript += transcript;
            }
        }
        
        final_span.innerHTML = finalTranscript;
        interim_span.innerHTML = interimTranscript;
        final_span_Handler();

        console.log('finalTranscript', finalTranscript);
        console.log('interimTranscript', interimTranscript);
        // fireCommand(interimTranscript);
    };

    /**
     * 음성 인식 에러 처리
     */
    recognition.onerror = function (event) {
        console.log('onerror', event);

        if (event.error.match(/no-speech|audio-capture|not-allowed/)) {
        ignoreEndProcess = true;
        }

        micBtn.classList.add();
    };

    /**
     * 명령어 처리
     * @param string
     */
    // function fireCommand(string) {
    //     if (string.endsWith('레드')) {
    //     $resultWrap.className = 'red';
    //     } else if (string.endsWith('블루')) {
    //     $resultWrap.className = 'blue';
    //     } else if (string.endsWith('그린')) {
    //     $resultWrap.className = 'green';
    //     } else if (string.endsWith('옐로우')) {
    //     $resultWrap.className = 'yellow';
    //     } else if (string.endsWith('오렌지')) {
    //     $resultWrap.className = 'orange';
    //     } else if (string.endsWith('그레이')) {
    //     $resultWrap.className = 'grey';
    //     } else if (string.endsWith('골드')) {
    //     $resultWrap.className = 'gold';
    //     } else if (string.endsWith('화이트')) {
    //     $resultWrap.className = 'white';
    //     } else if (string.endsWith('블랙')) {
    //     $resultWrap.className = 'black';
    //     } else if (string.endsWith('알람') || string.endsWith('알 람')) {
    //     alert('알람');
    //     } else if (string.endsWith('노래 켜') || string.endsWith('음악 켜')) {
    //     $audio.play();
    //     $iconMusic.classList.add('visible');
    //     } else if (string.endsWith('노래 꺼') || string.endsWith('음악 꺼')) {
    //     $audio.pause();
    //     $iconMusic.classList.remove('visible');
    //     } else if (string.endsWith('볼륨 업') || string.endsWith('볼륨업')) {
    //     $audio.volume += 0.2;
    //     } else if (string.endsWith('볼륨 다운') || string.endsWith('볼륨다운')) {
    //     $audio.volume -= 0.2;
    //     } else if (string.endsWith('스피치') || string.endsWith('말해줘') || string.endsWith('말 해 줘')) {
    //     textToSpeech($('#final_span').text() || '전 음성 인식된 글자를 읽습니다.');
    //     }
    // }

    /**
     * 음성 인식 트리거
     *  마이크 버튼 눌렀을때
     */
    function start() {
        if (isRecognizing) { //이건 버튼을 두번 누른거니까 종료시킨다.
            recognition.stop();
            console.log('stopped');
            return;
        }
        recognition.lang = language;
        recognition.start(); //이게 호출되면 일단 음성인식 시작된 것.
        ignoreEndProcess = false;

        finalTranscript = '';
        final_span.innerHTML = '';
        interim_span.innerHTML = '';
    }
    function delBtnHandler() {
        final_span.innerHTML = '';
    }
    /**
     * 초기 바인딩
     */
    function resultWordHandler(event) {
        console.log('clicked id : ' + event.target.value);
    }

    function final_span_Handler() {
        if(final_span.innerHTML) {
            const final_span_text = final_span.innerHTML; //final_span = "안녕하세요 저는 정이든 입니다."
            const final_arr = final_span_text.split(' '); //["안녕하세요", "저는"]
            
            let htmlEl = null;
            final_arr.forEach((value, index) => {
                if(index === 0) {
                    htmlEl = `<span class="resultWord" id=0>` + value + '<span/>';
                }else {
                    htmlEl = htmlEl + `<span class="resultWord" id=${index}>${value}<span/> ` 
                }
            });
            console.log('htmlEl : ' + htmlEl);
            
            // const resultWord = document.querySelector('.resultWord');
            // resultWord.addEventListener('click', resultWordHandler);
            final_span.innerHTML = htmlEl;
        }else {
            return null;
        }
    }
    function initialize() {
        micBtn.addEventListener('click', start);
        delBtn.addEventListener('click', delBtnHandler);
        
        //마이크 버튼 누르면 시작
    }
    
    initialize();
}