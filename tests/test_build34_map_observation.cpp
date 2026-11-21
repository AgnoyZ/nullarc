// SPDX-License-Identifier: MIT
// Executes the actual staged start() mapping block with CPU-only property/map
// doubles. The map exposes metadata getters only; no BAR pointer/read/write API.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <string>
static unsigned checks=0;
#define CHECK(x) do { ++checks; if(!(x)){std::fprintf(stderr,"failed %d: %s\n",__LINE__,#x);std::_Exit(86);} } while(0)
using IOOptionBits=uint32_t;
static constexpr uint32_t kIOMapCacheMask=0xf00,kIOMapCacheShift=8;
struct Map {
    uint32_t options=0,optionReads=0,lengthReads=0,physicalReads=0;
    uint64_t getLength(){++lengthReads;return 0x10000000;}
    uint64_t getPhysicalAddress(){++physicalReads;return 0x100000000;}
    IOOptionBits getMapOptions(){++optionReads;return options;}
};
struct Service {
    Map *fbAper=nullptr;
    uint64_t fbAperLen=0,fbAperPhys=0;
    unsigned failures=0;
    std::map<std::string,uint64_t> properties;
    bool setProperty(const char *key,uint64_t value,unsigned bits){
        CHECK(bits==32);
        unsigned bit=std::string(key)=="phx-bar0-map-options"?1:
                     std::string(key)=="phx-bar0-map-cache-option"?2:
                     std::string(key)=="phx-bar0-map-observation-version"?4:0;
        CHECK(bit!=0);
        if(failures&bit)return false;
        CHECK(properties.emplace(key,value).second);
        return true;
    }
    void observe(){
// PHX34_MAPPING_BLOCK
    }
};
int main(){
    Service absent;
    absent.observe();
    CHECK(absent.properties.empty()&&absent.fbAperLen==0&&absent.fbAperPhys==0);
    unsigned scenarios=1;
    for(uint32_t cache=0;cache<16;++cache){
        for(uint32_t flags:{0u,1u,0xfffff0ffu}){
            for(unsigned failures=0;failures<8;++failures){
                ++scenarios;
                Map map;map.options=flags|(cache<<8);
                Service s;s.fbAper=&map;s.failures=failures;
                s.observe();
                CHECK(map.options==(flags|(cache<<8)));
                CHECK(map.optionReads==1&&map.lengthReads==1&&map.physicalReads==1);
                CHECK(s.fbAperLen==0x10000000&&s.fbAperPhys==0x100000000);
                CHECK(s.properties.count("phx-bar0-map-options")==!(failures&1));
                CHECK(s.properties.count("phx-bar0-map-cache-option")==!(failures&2));
                const bool marker=failures==0;
                CHECK(s.properties.count("phx-bar0-map-observation-version")==marker);
                if(!(failures&1))CHECK(s.properties.at("phx-bar0-map-options")==map.options);
                if(!(failures&2))CHECK(s.properties.at("phx-bar0-map-cache-option")==cache);
                if(marker)CHECK(s.properties.at("phx-bar0-map-observation-version")==1);
            }
        }
    }
    std::printf("%u checks / %u mapping metadata scenarios\n",checks,scenarios);
}
