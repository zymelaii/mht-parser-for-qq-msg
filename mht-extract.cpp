#include <iostream>
#include <assert.h>
#include <map>
#include <filesystem>
#include <regex>
#include <string>
#include <string_view>
#include <stdlib.h>
#include <fstream>
#include <algorithm>
#include <ctype.h>
#include <stdint.h>
#include <cstddef>
#include <string.h>
#include "base64.h"

namespace fs = std::filesystem;

enum class ContentType {
    Unknown,
    Html,
    Jpeg,
    Png,
    Gif,
};

struct PartHeader {
    ContentType type;
    std::string file;
    std::string encoding;
};

std::string lstrip(const std::string &s) {
    auto       result = s;
    const auto pred   = [](unsigned char ch) {
        return !isspace(ch);
    };
    const auto it = std::find_if(result.begin(), result.end(), pred);
    result.erase(result.begin(), it);
    return result;
}

std::string rstrip(const std::string &s) {
    auto       result = s;
    const auto pred   = [](unsigned char ch) {
        return !isspace(ch);
    };
    const auto it = std::find_if(result.rbegin(), result.rend(), pred).base();
    result.erase(it, result.end());
    return result;
}

std::string strip(const std::string &s) {
    return lstrip(rstrip(s));
}

void print_help_info(const char *exec) {
    std::cout << "USAGE: " << exec << " [options] <path-to-mht>\n";
    std::cout << "\n";
    std::cout << "OPTIONS:\n";
    std::cout << "  -H <dir>    where to place the extracted html docs\n";
    std::cout << "  -A <dir>    where to place the extracted attachments\n";
    std::cout << std::endl;
}

void skip_utf8_signature(std::ifstream &file) {
    const auto pos    = file.tellg();
    uint8_t    sig[3] = {};
    file.read(reinterpret_cast<char *>(sig), 3);
    if (!(sig[0] == 0xef && sig[1] == 0xbb && sig[2] == 0xbf)) {
        file.seekg(pos);
    }
}

void prepare_dir(const char *html_dir, const char *attachment_dir) {
    bool dir_ok = false;

    if (fs::exists(html_dir)) {
        if (fs::is_directory(html_dir)) { dir_ok = true; }
    } else if (fs::create_directory(html_dir)) {
        dir_ok = true;
    }
    if (!dir_ok) {
        std::cerr << "error: cannot create html dir " << html_dir << std::endl;
        exit(EXIT_FAILURE);
    }

    if (fs::exists(attachment_dir)) {
        if (fs::is_directory(attachment_dir)) { dir_ok = true; }
    } else if (fs::create_directory(attachment_dir)) {
        dir_ok = true;
    }
    if (!dir_ok) {
        std::cerr << "error: cannot create attachment dir " << attachment_dir
                  << std::endl;
        exit(EXIT_FAILURE);
    }
}

int main(int argc, char *argv[]) {
    const char *html_dir       = "html";
    const char *attachment_dir = "res";
    const char *mht_doc        = nullptr;

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "-H") == 0) {
            if (++i < argc) { html_dir = argv[i]; }
        } else if (strcmp(argv[i], "-A") == 0) {
            if (++i < argc) { attachment_dir = argv[i]; }
        } else {
            mht_doc = argv[i];
        }
    }

    if (!mht_doc) {
        print_help_info(argv[0]);
        return EXIT_FAILURE;
    }

    prepare_dir(html_dir, attachment_dir);

    std::ifstream mht(mht_doc);
    if (!mht.is_open()) {
        std::cerr << "error: failed to open " << mht_doc << std::endl;
        return EXIT_FAILURE;
    }

    std::cout << "info: extract resources from " << mht_doc << std::endl;
    std::cout << "info: html will be extracted to " << html_dir << std::endl;
    std::cout << "info: images will be extracted to " << attachment_dir
              << std::endl;

    skip_utf8_signature(mht);

    std::string buf{};

    //! find boundary
    std::string      bd{};
    const std::regex pat("boundary=\"(.*)\"$");
    std::smatch      result{};
    while (true) {
        std::getline(mht, buf);
        bool found = std::regex_search(buf, result, pat);
        if (!found) { continue; }
        bd = "--" + result.str(1);
        break;
    }

    //! find first part
    while (!mht.eof()) {
        std::getline(mht, buf);
        if (buf.find(bd) == 0) { break; }
    }

    const std::map<std::string, ContentType> ContentTypeLookup{
        {"text/html",  ContentType::Html},
        {"image/jpeg", ContentType::Jpeg},
        {"image/png",  ContentType::Png },
        {"image/gif",  ContentType::Gif },
    };

    int total_html  = 0;
    int total_image = 0;

    while (true) {
        if (buf.size() == bd.size() + 2 && buf.substr(buf.size() - 2) == "--") {
            break;
        }

        PartHeader header{.type = ContentType::Unknown};

        //! parse header of part
        int total_header = 0;
        while (!mht.eof()) {
            std::getline(mht, buf);
            const auto pos = buf.find(":");
            if (pos == buf.npos) { break; }

            const auto key   = strip(buf.substr(0, pos));
            const auto value = strip(buf.substr(pos + 1));

            if (key == "Content-Type") {
                if (ContentTypeLookup.count(value)) {
                    header.type = ContentTypeLookup.at(value);
                }
            } else if (key == "Content-Location") {
                header.file = value;
            } else if (key == "Content-Transfer-Encoding") {
                header.encoding = value;
            }

            ++total_header;
        }

        //! rename file name of images
        if (!header.file.empty()) {
            auto prefix = header.file.substr(0, header.file.rfind("."));
            std::transform(
                prefix.begin(), prefix.end(), prefix.begin(), toupper);
            switch (header.type) {
                case ContentType::Jpeg: {
                    header.file = prefix + ".jpg";
                } break;
                case ContentType::Png: {
                    header.file = prefix + ".png";
                } break;
                case ContentType::Gif: {
                    header.file = prefix + ".gif";
                } break;
                default: {
                } break;
            }
        }

        //! NOTE: html doc may be very large, use stream ops instead of read all
        //! into memory
        if (header.type == ContentType::Html) {
            const auto file = "index-" + std::to_string(++total_html) + ".html";
            std::ofstream html(fs::path(html_dir) / file);
            while (!mht.eof()) {
                std::getline(mht, buf);
                if (buf.find(bd) == 0) { break; }
                html << buf;
            }
            std::clog << "write out html to " << file << std::endl;
            continue;
        }

        std::string content{};
        while (!mht.eof()) {
            std::getline(mht, buf);
            if (buf.find(bd) == 0) { break; }
            content += buf;
        }

        if (header.type == ContentType::Unknown) { continue; }

        //! NOTE: support base64 encoded image only
        if (!header.encoding.empty() && header.encoding != "base64") {
            continue;
        }

        const auto    bytes = base64::decode_into<std::vector<char>>(content);
        std::ofstream image(
            fs::path(attachment_dir) / header.file,
            std::ios::trunc | std::ios::binary);
        image.write(bytes.data(), bytes.size());
        std::clog << "write out image (" << ++total_image << ") to "
                  << header.file << std::endl;
    }

    return EXIT_SUCCESS;
}
