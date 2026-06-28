cmake_minimum_required(VERSION 3.16)
project(prime_ramulator_bridge LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(RAMULATOR_ROOT "${CMAKE_CURRENT_LIST_DIR}/..")

add_library(prime_ramulator_bridge SHARED
  prime_ramulator_bridge.cpp
)

target_include_directories(prime_ramulator_bridge PUBLIC
  "${CMAKE_CURRENT_LIST_DIR}"
  "${RAMULATOR_ROOT}/src"
)

target_link_libraries(prime_ramulator_bridge PRIVATE
  "${RAMULATOR_ROOT}/libramulator.so"
)

set_target_properties(prime_ramulator_bridge PROPERTIES
  BUILD_RPATH "${RAMULATOR_ROOT}"
  INSTALL_RPATH "${RAMULATOR_ROOT}"
)

add_executable(test_bridge
  test_bridge.cpp
)

target_include_directories(test_bridge PUBLIC
  "${CMAKE_CURRENT_LIST_DIR}"
  "${RAMULATOR_ROOT}/src"
)

target_link_libraries(test_bridge PRIVATE
  prime_ramulator_bridge
)

set_target_properties(test_bridge PROPERTIES
  BUILD_RPATH "${RAMULATOR_ROOT};${CMAKE_CURRENT_BINARY_DIR}"
  INSTALL_RPATH "${RAMULATOR_ROOT};${CMAKE_CURRENT_BINARY_DIR}"
)





add_executable(test_prime_direct test_prime_direct.cpp)

target_link_libraries(test_prime_direct PRIVATE
  prime_ramulator_bridge
  ${CMAKE_SOURCE_DIR}/../libramulator.so
)

target_link_options(test_prime_direct PRIVATE
  "-Wl,-rpath,${CMAKE_SOURCE_DIR}/../"
)

