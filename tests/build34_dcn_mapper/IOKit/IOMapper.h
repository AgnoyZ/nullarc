#pragma once

#include <string>
#include <utility>
#include <vector>

class OSObject {
public:
    virtual ~OSObject() = default;
    void retain() { ++references; }
    void release() {
        if (--references == 0) delete this;
    }
    unsigned referenceCount() const { return references; }

private:
    unsigned references = 1;
};

class OSString : public OSObject {
public:
    explicit OSString(std::string value) : value(std::move(value)) {}
    unsigned getLength() const { return static_cast<unsigned>(value.size()); }
    bool isEqualTo(const OSString *other) const { return other && value == other->value; }

private:
    std::string value;
};

class OSSymbol : public OSString {
public:
    using OSString::OSString;
};

class OSDictionary : public OSObject {
public:
    ~OSDictionary() override {
        if (mapperID) mapperID->release();
    }
    bool setObject(const OSSymbol *key, OSString *value);
    bool matches(const OSSymbol *key, const OSString *value) const;

private:
    OSString *mapperID = nullptr;
};

class OSIterator : public OSObject {
public:
    explicit OSIterator(std::vector<OSObject *> values, bool valid)
        : values(std::move(values)), valid(valid) {}
    OSObject *getNextObject() {
        if (index == values.size()) return nullptr;
        return values[index++];
    }
    bool isValid() const { return valid; }

private:
    std::vector<OSObject *> values;
    std::size_t index = 0;
    bool valid;
};

class IOMapper;

namespace fake_dcn_mapper {
extern std::vector<IOMapper *> mapperServices;
extern unsigned serviceMatchingCalls;
extern unsigned matchingServicesCalls;
extern bool serviceMatchingFails;
extern bool setObjectFails;
extern bool matchingServicesFails;
extern bool iteratorIsValid;
}

class IOService : public OSObject {
public:
    virtual bool isInactive() const { return inactive; }
    virtual OSObject *getProperty(const char *key) const {
        return key && std::string(key) == "iommu-parent" ? mapperParent : nullptr;
    }
    static OSDictionary *serviceMatching(const char *className);
    static OSIterator *getMatchingServices(OSDictionary *matching);
    void setMapperParent(OSObject *parent) { mapperParent = parent; }
    void setInactive(bool value) { inactive = value; }

private:
    OSObject *mapperParent = nullptr;
    bool inactive = false;
};

class IOMapper : public IOService {
public:
    explicit IOMapper(OSString *identifier) : identifier(identifier) {}
    OSString *mapperIdentifier() const { return identifier; }

private:
    OSString *identifier;
};

namespace fake_dcn_mapper {
extern const OSSymbol mapperIDKey;
}

inline const OSSymbol *gIOMapperIDKey = &fake_dcn_mapper::mapperIDKey;

inline bool OSDictionary::setObject(const OSSymbol *key, OSString *value) {
    if (!key || !value || fake_dcn_mapper::setObjectFails || mapperID) return false;
    mapperID = value;
    mapperID->retain();
    return true;
}

inline bool OSDictionary::matches(const OSSymbol *key, const OSString *value) const {
    return key == gIOMapperIDKey && mapperID && mapperID->isEqualTo(value);
}

inline OSDictionary *IOService::serviceMatching(const char *className) {
    ++fake_dcn_mapper::serviceMatchingCalls;
    if (!className || std::string(className) != "IOMapper" || fake_dcn_mapper::serviceMatchingFails) return nullptr;
    return new OSDictionary;
}

inline OSIterator *IOService::getMatchingServices(OSDictionary *matching) {
    ++fake_dcn_mapper::matchingServicesCalls;
    if (!matching || fake_dcn_mapper::matchingServicesFails) return nullptr;
    std::vector<OSObject *> result;
    for (IOMapper *mapper : fake_dcn_mapper::mapperServices) {
        if (mapper && matching->matches(gIOMapperIDKey, mapper->mapperIdentifier())) result.push_back(mapper);
    }
    return new OSIterator(std::move(result), fake_dcn_mapper::iteratorIsValid);
}

#define OSDynamicCast(type, object) dynamic_cast<type *>(object)
