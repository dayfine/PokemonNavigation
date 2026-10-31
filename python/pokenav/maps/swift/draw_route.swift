import CoreGraphics; import ImageIO; import Foundation; import UniformTypeIdentifiers
let a=CommandLine.arguments
let src=CGImageSourceCreateWithURL(URL(fileURLWithPath:a[1]) as CFURL,nil)!; let img=CGImageSourceCreateImageAtIndex(src,0,nil)!
let W=img.width,H=img.height
let ctx=CGContext(data:nil,width:W,height:H,bitsPerComponent:8,bytesPerRow:0,space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)!
ctx.draw(img,in:CGRect(x:0,y:0,width:W,height:H))
// tile grid, light
ctx.setStrokeColor(CGColor(red:1,green:1,blue:1,alpha:0.18)); ctx.setLineWidth(1)
for x in stride(from:0,to:W,by:16){ctx.move(to:CGPoint(x:x,y:0));ctx.addLine(to:CGPoint(x:x,y:H))}
for y in stride(from:0,to:H,by:16){ctx.move(to:CGPoint(x:0,y:H-y));ctx.addLine(to:CGPoint(x:W,y:H-y))}
ctx.strokePath()
// grid overlay from a[4]: first line "ox oy", then rows
if a.count > 4 {
  let lines=try! String(contentsOfFile:a[4]).split(separator:"\n").map(String.init)
  let o=lines[0].split(separator:" ").map{Int($0)!}
  for (ty,row) in lines.dropFirst().enumerated(){
    for (tx,ch) in row.enumerated(){
      if ch == "." { continue }
      ctx.setFillColor(ch == "#" ? CGColor(red:1,green:0,blue:0,alpha:0.30) : CGColor(red:1,green:0.9,blue:0,alpha:0.35))
      ctx.fill(CGRect(x:o[0]+tx*16,y:H-(o[1]+ty*16)-16,width:16,height:16))
    }
  }
}
// route from args: x,y pairs
if a[3].isEmpty { } 
let pts=a[3].isEmpty ? [[0.0,0.0]] : a[3].split(separator:" ").map{ $0.split(separator:",").map{Double($0)!} }
ctx.setStrokeColor(CGColor(red:1,green:0.1,blue:0.1,alpha:0.95)); ctx.setLineWidth(5); ctx.setLineJoin(.round)
ctx.move(to:CGPoint(x:pts[0][0],y:Double(H)-pts[0][1]))
for p in pts.dropFirst(){ctx.addLine(to:CGPoint(x:p[0],y:Double(H)-p[1]))}
ctx.strokePath()
for (i,p) in pts.enumerated(){
  ctx.setFillColor(i==0 ? CGColor(red:0,green:0.8,blue:0,alpha:1) : (i==pts.count-1 ? CGColor(red:1,green:0.85,blue:0,alpha:1) : CGColor(red:1,green:1,blue:1,alpha:1)))
  ctx.fillEllipse(in:CGRect(x:p[0]-7,y:Double(H)-p[1]-7,width:14,height:14))
}
let out=ctx.makeImage()!
let d=CGImageDestinationCreateWithURL(URL(fileURLWithPath:a[2]) as CFURL,UTType.png.identifier as CFString,1,nil)!
CGImageDestinationAddImage(d,out,nil); CGImageDestinationFinalize(d)
