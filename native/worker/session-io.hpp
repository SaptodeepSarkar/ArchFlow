// Private inherited-pipe protocol, never the UI/control socket or a TCP service.
#pragma once
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include "json.hpp"
using json = nlohmann::json;
inline bool frame(std::string &body, uint32_t limit) {
    unsigned char header[4];
    std::cin.read(reinterpret_cast<char *>(header), 4);
    if (std::cin.gcount() == 0) return false;
    if (std::cin.gcount() != 4) throw std::runtime_error("frame");
    uint32_t size = uint32_t(header[0]) << 24 | uint32_t(header[1]) << 16 | uint32_t(header[2]) << 8 | header[3];
    if (size > limit) throw std::runtime_error("limit");
    body.resize(size); std::cin.read(body.data(), size);
    if (std::cin.gcount() != size) throw std::runtime_error("truncated");
    return true;
}
inline void reply(const json &value) {
    std::string body = value.dump();
    if (body.size() > 65536) throw std::runtime_error("output limit");
    uint32_t n = body.size();
    unsigned char header[4] = { static_cast<unsigned char>(n >> 24), static_cast<unsigned char>(n >> 16), static_cast<unsigned char>(n >> 8), static_cast<unsigned char>(n) };
    std::cout.write(reinterpret_cast<char *>(header), 4); std::cout.write(body.data(), body.size()); std::cout.flush();
}
