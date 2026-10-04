// Model context is owned by one worker process; stdin EOF releases it.
#include "session-io.hpp"
#include "whisper.h"
#include <algorithm>
#include <chrono>
#include <cstring>
#include <memory>
#include <vector>
static void quiet(enum ggml_log_level, const char *, void *) {}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    whisper_log_set(quiet, nullptr);
    auto cp = whisper_context_default_params(); cp.use_gpu = false;
    std::unique_ptr<whisper_context, decltype(&whisper_free)> model(whisper_init_from_file_with_params(argv[1], cp), whisper_free);
    if (!model) return 3;
    try {
        std::string header, pcm;
        while (frame(header, 65536)) {
            auto request = json::parse(header);
            if (!frame(pcm, 120 * 16000 * 4) || pcm.empty() || pcm.size() % 4) return 4;
            std::vector<float> samples(pcm.size()/4);
            std::memcpy(samples.data(), pcm.data(), pcm.size());
            auto p = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
            std::string language=request.value("language", "en"), prompt=request.value("prompt", "");
            p.language=language.c_str(); p.initial_prompt=prompt.c_str();
            p.n_threads=std::clamp(request.value("threads",2),1,16);
            p.translate=request.value("translate",false); p.no_context=true;
            p.print_realtime=false; p.print_progress=false; p.print_timestamps=false; p.print_special=false;
            auto start=std::chrono::steady_clock::now();
            if (whisper_full(model.get(),p,samples.data(),samples.size())) { reply({{"error","inference failed"}}); continue; }
            std::string text;
            for(int i=0;i<whisper_full_n_segments(model.get());++i) text += whisper_full_get_segment_text(model.get(),i);
            auto ms=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-start).count();
            reply({{"text",text},{"ms",ms}});
        }
    } catch (...) { return 5; }
    return 0;
}
