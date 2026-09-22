//! Portable V6 hashed-tagger package reader.
//!
//! The exporter writes little-endian float32 tensors with an explicit header so
//! Linux and Android loaders can share the same artifact.  This module only
//! parses and validates the package; platform runtimes own tokenization and
//! rendering, and must pass the frozen V6 challenge before promotion.

const MAGIC: &[u8; 8] = b"V6TG\x01\0\0\0";
const MAX_TENSORS: u32 = 64;
const MAX_DIMS: u32 = 4;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Tensor {
    pub name: String,
    pub dims: Vec<u32>,
    pub bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Package {
    pub tensors: Vec<Tensor>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Error {
    Truncated,
    BadMagic,
    InvalidCount,
    InvalidRank,
    InvalidDimensions,
    InvalidUtf8,
    DuplicateTensor(String),
    TrailingBytes,
}

fn take<'a>(data: &'a [u8], offset: &mut usize, size: usize) -> Result<&'a [u8], Error> {
    let end = offset.checked_add(size).ok_or(Error::Truncated)?;
    if end > data.len() { return Err(Error::Truncated); }
    let value = &data[*offset..end];
    *offset = end;
    Ok(value)
}

fn u32_le(data: &[u8], offset: &mut usize) -> Result<u32, Error> {
    Ok(u32::from_le_bytes(take(data, offset, 4)?.try_into().unwrap()))
}

pub fn parse(data: &[u8]) -> Result<Package, Error> {
    if take(data, &mut 0, MAGIC.len())? != MAGIC { return Err(Error::BadMagic); }
    let mut offset = MAGIC.len();
    let count = u32_le(data, &mut offset)?;
    if count == 0 || count > MAX_TENSORS { return Err(Error::InvalidCount); }
    let mut tensors = Vec::with_capacity(count as usize);
    for _ in 0..count {
        let name_len = u32_le(data, &mut offset)? as usize;
        if name_len == 0 || name_len > 256 { return Err(Error::InvalidDimensions); }
        let name = std::str::from_utf8(take(data, &mut offset, name_len)?)
            .map_err(|_| Error::InvalidUtf8)?.to_owned();
        if tensors.iter().any(|tensor: &Tensor| tensor.name == name) {
            return Err(Error::DuplicateTensor(name));
        }
        let rank = u32_le(data, &mut offset)?;
        if rank > MAX_DIMS { return Err(Error::InvalidRank); }
        let mut dims = Vec::with_capacity(rank as usize);
        let mut elements: usize = 1;
        for _ in 0..rank {
            let dim = u32_le(data, &mut offset)?;
            if dim == 0 { return Err(Error::InvalidDimensions); }
            elements = elements.checked_mul(dim as usize).ok_or(Error::InvalidDimensions)?;
            dims.push(dim);
        }
        let byte_len = elements.checked_mul(4).ok_or(Error::InvalidDimensions)?;
        let bytes = take(data, &mut offset, byte_len)?.to_vec();
        tensors.push(Tensor { name, dims, bytes });
    }
    if offset != data.len() { return Err(Error::TrailingBytes); }
    Ok(Package { tensors })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn package() -> Vec<u8> {
        let mut out = MAGIC.to_vec();
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&3u32.to_le_bytes());
        out.extend_from_slice(b"one");
        out.extend_from_slice(&2u32.to_le_bytes());
        out.extend_from_slice(&2u32.to_le_bytes());
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&[0; 8]);
        out
    }

    #[test]
    fn parses_float_tensor_envelope() {
        let parsed = parse(&package()).unwrap();
        assert_eq!(parsed.tensors[0].name, "one");
        assert_eq!(parsed.tensors[0].dims, vec![2, 1]);
        assert_eq!(parsed.tensors[0].bytes.len(), 8);
    }

    #[test]
    fn rejects_trailing_bytes() {
        let mut bytes = package();
        bytes.push(0);
        assert_eq!(parse(&bytes), Err(Error::TrailingBytes));
    }
}
