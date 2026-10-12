<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0"
    xmlns="http://www.opengis.net/sld"
    xmlns:ogc="http://www.opengis.net/ogc"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd">
  <NamedLayer>
    <Name>soil_moisture</Name>
    <UserStyle>
      <Name>soil_moisture</Name>
      <Title>Surface soil moisture (m³/m³)</Title>
      <Abstract>Continuous dry-to-wet ramp for EOS-04 SAR-MRS volumetric surface soil moisture.
        Valid product range is 0.02-0.65 m³/m³ (SAC ATBD, Dec 2023); nodata is transparent.</Abstract>
      <FeatureTypeStyle>
        <Rule>
          <Name>soil_moisture</Name>
          <RasterSymbolizer>
            <Opacity>1.0</Opacity>
            <ColorMap type="ramp">
              <ColorMapEntry color="#8c510a" quantity="0.02" opacity="1" label="0.02 dry"/>
              <ColorMapEntry color="#d8b365" quantity="0.10" opacity="1" label="0.10"/>
              <ColorMapEntry color="#f6e8c3" quantity="0.18" opacity="1" label="0.18"/>
              <ColorMapEntry color="#c7eae5" quantity="0.26" opacity="1" label="0.26"/>
              <ColorMapEntry color="#5ab4ac" quantity="0.34" opacity="1" label="0.34"/>
              <ColorMapEntry color="#01665e" quantity="0.45" opacity="1" label="0.45"/>
              <ColorMapEntry color="#08306b" quantity="0.65" opacity="1" label="0.65 wet"/>
            </ColorMap>
          </RasterSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
