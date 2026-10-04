// Retain only model weights between jobs; each job owns a fresh bounded context.
#include "session-io.hpp"
#include "llama.h"
#include <chrono>
#include <memory>
#include <vector>
static void quiet(enum ggml_log_level, const char *, void *) {}
int main(int argc,char **argv) {
    if(argc!=2) return 2;
    llama_log_set(quiet,nullptr); llama_backend_init();
    auto mp=llama_model_default_params();mp.n_gpu_layers=0;
    std::unique_ptr<llama_model,decltype(&llama_model_free)> model(llama_model_load_from_file(argv[1],mp),llama_model_free);
    if(!model) return 3;
    const auto *vocab=llama_model_get_vocab(model.get());
    try {
        std::string body;
        while(frame(body,65536)) {
            const auto prompt=json::parse(body).at("prompt").get<std::string>();
            int n=-llama_tokenize(vocab,prompt.data(),prompt.size(),nullptr,0,true,false);
            if(n<=0 || n>768) { reply({{"error","context limit"}});continue; }
            std::vector<llama_token> tokens(n);
            if(llama_tokenize(vocab,prompt.data(),prompt.size(),tokens.data(),n,true,false)<0) return 4;
            auto cp=llama_context_default_params();cp.n_ctx=1024;cp.n_batch=768;cp.n_threads=2;cp.n_threads_batch=2;cp.no_perf=true;
            std::unique_ptr<llama_context,decltype(&llama_free)> context(llama_init_from_model(model.get(),cp),llama_free);
            std::unique_ptr<llama_sampler,decltype(&llama_sampler_free)> sampler(llama_sampler_init_greedy(),llama_sampler_free);
            if(!context || !sampler) return 5;
            auto batch=llama_batch_get_one(tokens.data(),n);
            auto start=std::chrono::steady_clock::now();std::string text;llama_token token=0;bool failed=false;
            for(int i=0;i<256;++i) {
                if(llama_decode(context.get(),batch)) {failed=true;break;}
                token=llama_sampler_sample(sampler.get(),context.get(),-1);
                if(llama_vocab_is_eog(vocab,token)) break;
                char piece[512];int count=llama_token_to_piece(vocab,token,piece,sizeof(piece),0,false);
                if(count<0 || text.size()+count>65500) {failed=true;break;}
                text.append(piece,count);batch=llama_batch_get_one(&token,1);
            }
            auto ms=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-start).count();
            if(failed) reply({{"error","inference failed"}});else reply({{"text",text},{"ms",ms}});
        }
    } catch(...) { return 6; }
    return 0;
}
