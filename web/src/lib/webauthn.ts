// Minimal WebAuthn client — converts the server's base64url option fields to ArrayBuffers, drives
// navigator.credentials, and serializes the result back to base64url JSON for the server to verify.
// (Server options come from the python `webauthn` lib's options_to_json, i.e. base64url strings.)

function b64urlToBuf(s: string): ArrayBuffer {
  const pad = '='.repeat((4 - (s.length % 4)) % 4)
  const b64 = (s + pad).replace(/-/g, '+').replace(/_/g, '/')
  const bin = atob(b64)
  const buf = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i)
  return buf.buffer
}
function bufToB64url(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf)
  let bin = ''
  for (const b of bytes) bin += String.fromCharCode(b)
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

export function supported(): boolean {
  return typeof window !== 'undefined' && !!window.PublicKeyCredential && !!navigator.credentials
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function startRegistration(options: any): Promise<any> {
  const pk = { ...options }
  pk.challenge = b64urlToBuf(pk.challenge)
  pk.user = { ...pk.user, id: b64urlToBuf(pk.user.id) }
  if (pk.excludeCredentials) pk.excludeCredentials = pk.excludeCredentials.map((c: any) => ({ ...c, id: b64urlToBuf(c.id) }))
  const cred = (await navigator.credentials.create({ publicKey: pk })) as PublicKeyCredential
  const r = cred.response as AuthenticatorAttestationResponse
  return {
    id: cred.id, rawId: bufToB64url(cred.rawId), type: cred.type,
    response: { attestationObject: bufToB64url(r.attestationObject), clientDataJSON: bufToB64url(r.clientDataJSON) },
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function startAuthentication(options: any): Promise<any> {
  const pk = { ...options }
  pk.challenge = b64urlToBuf(pk.challenge)
  if (pk.allowCredentials) pk.allowCredentials = pk.allowCredentials.map((c: any) => ({ ...c, id: b64urlToBuf(c.id) }))
  const cred = (await navigator.credentials.get({ publicKey: pk })) as PublicKeyCredential
  const r = cred.response as AuthenticatorAssertionResponse
  return {
    id: cred.id, rawId: bufToB64url(cred.rawId), type: cred.type,
    response: {
      authenticatorData: bufToB64url(r.authenticatorData), clientDataJSON: bufToB64url(r.clientDataJSON),
      signature: bufToB64url(r.signature), userHandle: r.userHandle ? bufToB64url(r.userHandle) : null,
    },
  }
}
