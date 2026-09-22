//! Portable V6 hashed-tagger package reader.
//!
//! The exporter writes little-endian float32 tensors with an explicit header so
//! Linux and Android loaders can share the same artifact.  This module only
//! parses and validates the package; platform runtimes own tokenization and
//! rendering, and must pass the frozen V6 challenge before promotion.

const MAGIC: &[u8; 8] = b"V6TG\x01\0\0\0";
const MAX_TENSORS: u32 = 64;
const MAX_DIMS: u32 = 4;
const BUCKETS: usize = 2048;
const HIDDEN: usize = 96;
const MAX_FEATURES: usize = 10;

pub const TOKEN_LABELS: [&str; 6] = ["KEEP", "DELETE_FILLER", "DELETE_FALSE_START", "DELETE_RETRACTED", "CAPITALIZE", "NORMALIZE_ALLOWED"];
pub const PUNCTUATION: [&str; 7] = ["NONE", "COMMA", "PERIOD", "QUESTION_MARK", "EXCLAMATION_MARK", "COLON", "SEMICOLON"];

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
    MissingTensor(&'static str),
    InvalidTensor(&'static str),
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

fn hash_id(value: &str) -> usize {
    use blake2::{Blake2b, Digest};
    let mut hasher = Blake2b::<blake2::digest::consts::U4>::new();
    hasher.update(value.as_bytes());
    let digest = hasher.finalize();
    (u32::from_le_bytes(digest.into()) as usize) % BUCKETS
}

fn feature_ids(tokens: &[&str], index: usize) -> Vec<usize> {
    let lower = tokens[index].to_ascii_lowercase();
    let mut units = vec![format!("tok={lower}"), format!("pos={}", index.min(7)), format!("len={}", lower.len().min(12))];
    if index > 0 { units.push(format!("prev={}", tokens[index - 1].to_ascii_lowercase())); }
    if index + 1 < tokens.len() { units.push(format!("next={}", tokens[index + 1].to_ascii_lowercase())); }
    for j in 0..lower.len().saturating_sub(2) {
        units.push(format!("c3={}", &lower[j..j + 3]));
    }
    units.into_iter().take(MAX_FEATURES).map(|unit| hash_id(&unit)).collect()
}

fn tensor<'a>(package: &'a Package, name: &'static str) -> Result<&'a Tensor, Error> {
    package.tensors.iter().find(|item| item.name == name).ok_or(Error::MissingTensor(name))
}

fn values(item: &Tensor, name: &'static str) -> Result<Vec<f32>, Error> {
    if item.bytes.len() % 4 != 0 { return Err(Error::InvalidTensor(name)); }
    Ok(item.bytes.chunks_exact(4).map(|bytes| f32::from_le_bytes(bytes.try_into().unwrap())).collect())
}

fn linear(weights: &[f32], bias: &[f32], input: &[f32], output: usize) -> Vec<f32> {
    (0..output).map(|row| bias[row] + (0..input.len()).map(|col| weights[row * input.len() + col] * input[col]).sum::<f32>()).collect()
}

/// Run the bounded hashed tagger's token and sentence heads. Rendering remains
/// outside this primitive so both desktop and mobile can share safety policy.
pub fn predict(package: &Package, tokens: &[&str]) -> Result<(Vec<usize>, Vec<usize>), Error> {
    let embedding = values(tensor(package, "embedding.weight")?, "embedding.weight")?;
    let body_w = values(tensor(package, "body.0.weight")?, "body.0.weight")?;
    let body_b = values(tensor(package, "body.0.bias")?, "body.0.bias")?;
    let token_w = values(tensor(package, "token.weight")?, "token.weight")?;
    let token_b = values(tensor(package, "token.bias")?, "token.bias")?;
    let punct_w = values(tensor(package, "punct.weight")?, "punct.weight")?;
    let punct_b = values(tensor(package, "punct.bias")?, "punct.bias")?;
    if embedding.len() != BUCKETS * HIDDEN || body_w.len() != HIDDEN * HIDDEN || body_b.len() != HIDDEN || token_w.len() != 6 * HIDDEN || token_b.len() != 6 || punct_w.len() != 7 * HIDDEN || punct_b.len() != 7 { return Err(Error::InvalidTensor("tagger shape")); }
    let mut token_predictions = Vec::with_capacity(tokens.len());
    let mut punct_predictions = Vec::with_capacity(tokens.len());
    for index in 0..tokens.len() {
        let mut summed = vec![0.0; HIDDEN];
        for bucket in feature_ids(tokens, index) { for col in 0..HIDDEN { summed[col] += embedding[bucket * HIDDEN + col]; } }
        let hidden: Vec<f32> = linear(&body_w, &body_b, &summed, HIDDEN).into_iter().map(|value| value.max(0.0)).collect();
        let token_logits = linear(&token_w, &token_b, &hidden, 6);
        let punct_logits = linear(&punct_w, &punct_b, &hidden, 7);
        token_predictions.push(argmax(&token_logits));
        punct_predictions.push(argmax(&punct_logits));
    }
    Ok((token_predictions, punct_predictions))
}

fn argmax(values: &[f32]) -> usize {
    values.iter().enumerate().max_by(|(_, left), (_, right)| left.total_cmp(right)).map(|(index, _)| index).unwrap_or(0)
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
