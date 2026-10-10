#pragma once
#include <cstdint>
inline uint32_t testRandom=1;
inline uint32_t esp_random() { return ++testRandom; }
