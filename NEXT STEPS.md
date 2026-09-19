TASKS

1. in "Detection pack missing" give option to delete the models. where it should remove the models from my place also. where i need delete button when clicked shows a confirmation. and when okayed i want it to delete the model from its root path and clean up things related to that particular model

2. i want you to solve something here:
2:08:25 AM Extracting frames...
2:08:30 AM Processing 900 frames with 2 threads...
2:08:30 AM Progressing...
2:08:30 AM Processing video with 'simple' mode.
2:08:31 AM Error during source image reading or analysis D:\0 AMAAN MAIN\Codes and Tools\My Python & AI ML\AI\deep-image-video-face-swap\temp\uploads\3590c6181dd94db8ab7516e853d71b36\source.jpg: [ONNXRuntimeError] : 1 : FAIL : CUDA failure 900: operation not permitted when stream is capturing ; GPU=0 ; hostname=AMAAN-IDEAPAD-3 ; file=E:\_work\1\s\onnxruntime\core\providers\cuda\cuda_execution_provider.cc ; line=534 ; expr=cudaStreamSynchronize(static_cast<cudaStream_t>(stream_));
2:08:31 AM Halting video processing: Invalid or no face detected in source image for simple mode.
2:08:31 AM Error during source image reading or analysis D:\0 AMAAN MAIN\Codes and Tools\My Python & AI ML\AI\deep-image-video-face-swap\temp\uploads\3590c6181dd94db8ab7516e853d71b36\source.jpg: [ONNXRuntimeError] : 1 : FAIL : Non-zero status code returned while running Conv node. Name:'Conv_0' Status Message: CUDA error cudaErrorStreamCaptureUnsupported:operation not permitted when stream is capturing
2:08:31 AM Halting video processing: Invalid or no face detected in source image for simple mode.
8ab7516e853d71b36 HTTP/1.1" 200 OK
..................
Processing:  70%|███████████████████████▏         | 633/900 [04:00<03:58,  1.12frame/s, execution_providers=['CUDAExecutionProvider', 'CPUExecutionProvider'], execution_threads=2, max_memory=8]INFO:     127.0.0.1:46909 - "GET /api/jobs/3590c6181dd94db8ab7516e853d71b36 HTTP/1.1" 200 OK
Processing:  71%|███████████████████████▎         | 637/900 [04:03<03:53,  1.13 ..........

- where use full cpu threads and also use full gpu capability and do the parrallel processing to makes things faster. push to my full system capability. (you can give one shot pwsh command to check things if you want). should use all threads
- also sometimes there will face and sometimes there will not be a face so i want you to see if the current code handles that during the video time, for these edge cases

3. for just 30 second video it took 10 - 13 min. i want it to make the things faster. (even if i took quality it should be proper)

4. mention in my code what are the things that is unused and not even needed for future uses. (and can be deleted folders/files)

dont run anything in the sand box, just present the code after changes