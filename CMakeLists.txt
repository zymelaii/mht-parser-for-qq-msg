cmake_minimum_required(VERSION 3.5)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

project(mht-parser-for-qq-msg)

add_executable(mht-extract mht-extract.cpp)

include(GNUInstallDirs)
set(PROJECT_EXPORT_TARGETS mht-extract)
set(PROJECT_EXPORT_NAME ${PROJECT_NAME})
install(
    TARGETS ${PROJECT_EXPORT_TARGETS}
    RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}
)
