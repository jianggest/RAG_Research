## Digital Visual Interface DVI

## Revision 1.0

## 02 April 1999

The Digital Display Working Group Promoters ('DDWG Promoters') are Intel Corporation, Silicon Image, Inc., Compaq  Computer  Corporation,  Fujitsu  Limited,  Hewlett-Packard  Company,  International  Business Machines Corporation, and NEC Corporation

THIS SPECIFICATION IS PROVIDED "AS IS" WITH NO WARRANTIES WHATSOEVER, INCLUDING ANY WARRANTY  OF  MERCHANTABILITY,  NONINFRINGEMENT,  FITNESS  FOR  ANY  PARTICULAR PURPOSE, OR ANY WARRANTY OTHERWISE ARISING OUT OF ANY PROPOSAL, SPECIFICATION OR SAMPLE.

The DDWG Promoters disclaim all liability, including liability for infringement of any proprietary rights, relating to use of information in this specification. No license, express or implied, by estoppel or otherwise, to any intellectual property rights is granted herein.

The DDWG Promoters may have patents and/or patent applications related to the Digital Visual Interface Specification . The DDWG Promoters intend to make available to the industry an Adopter's Agreement that will include a limited, reciprocal, royalty-free license to the electrical interfaces, mechanical interfaces, signals, signaling and coding protocols, and bus protocols described in, and required by, the Digital Visual Interface Specification Revision 1.0 finalized and published by the DDWG Promoters.  To encourage early adoption, Adopters will be required to return their executed copy of the Adopter's Agreement during an 'Adoption Period' which is within one year after the DVI Specification Revision  1.0  is  first  published  or  within  one  year  after  the  Adopter  first  sells  products  that  comply  with  that specification,  whichever  is  later.    This  Adoption Period  requirement  will  give  parties  ample  time  to  understand  the benefits of becoming an Adopter and encourage them to remember this important step.

Copyright © DDWG Promoters 1999.

*Third-party brands and names are the property of their respective owners.

## Acknowledgement

The DDWG acknowledges the concerted efforts of employees of Silicon Image, Inc. and Molex Inc., who authored major portions of this specification. Both companies have made a significant contribution by developing and licensing to the industry the core technologies upon which this industry specification is based; transition minimized differential signaling (T.M.D.S.) technology from Silicon Image, and connector technology from Molex.

## REVISION HISTORY

02 Apr 99 - 1.0 Initial Specification Release

| Acknowledgement......................................................................................................2   | Acknowledgement......................................................................................................2                                                                                                                |                                                                                                                                                          |
|--------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------|
| REVISION HISTORY...................................................................................................2     | REVISION HISTORY...................................................................................................2                                                                                                                  |                                                                                                                                                          |
| 1.                                                                                                                       | Introduction................................................................................................5                                                                                                                         |                                                                                                                                                          |
| 1.1.                                                                                                                     | Scope and Motivation ................................                                                                                                                                                                                 | ................................ .......................5                                                                                                |
| 1.2.                                                                                                                     | Performance Scalability                                                                                                                                                                                                               | ................................ ....................6                                                                                                   |
| 1.2.1.                                                                                                                   | ................................ Bandwidth Estimation....................................................................................7                                                                                            |                                                                                                                                                          |
| 1.2.2.                                                                                                                   | Conversion to Selective Refresh...................................................................8                                                                                                                                   |                                                                                                                                                          |
| 1.3.                                                                                                                     | Related Documents                                                                                                                                                                                                                     | ..........................8                                                                                                                              |
| 1.3.1.                                                                                                                   | ................................ ................................ VESA Display Data Channel (DDC) Specification                                                                                                                       | ........................................8                                                                                                                |
| 1.3.2.                                                                                                                   | VESA Extended Display Identification Data (EDID) Specification                                                                                                                                                                        | ................8                                                                                                                                        |
| 1.3.3.                                                                                                                   | VESA Video Signal Standard (VSIS) Specification.......................................8                                                                                                                                               |                                                                                                                                                          |
| 1.3.4.                                                                                                                   | VESA Monitor Timing Specifications (DMT)                                                                                                                                                                                              | .................................................9                                                                                                       |
| 1.3.5.                                                                                                                   | VESA Generalized Timing Formula Specification (GTF)..............................9                                                                                                                                                    |                                                                                                                                                          |
| 1.3.6.                                                                                                                   | VESA Timing Definition for LCD Monitors Specification                                                                                                                                                                                 | ...............................9                                                                                                                         |
| 1.3.7.                                                                                                                   | Compatibility with Other T.M.D.S. Based Implementations.                                                                                                                                                                              | .........................9                                                                                                                               |
| 2.                                                                                                                       | Architectural Requirements...................................................................10                                                                                                                                       |                                                                                                                                                          |
| 2.1.                                                                                                                     | T.M.D.S. Overview................................                                                                                                                                                                                     | ................................ ..........................10                                                                                            |
| 2.2.                                                                                                                     | Plug and Play Specification ................................                                                                                                                                                                          | ................................ ............10                                                                                                          |
| 2.2.1.                                                                                                                   | Overview......................................................................................................10                                                                                                                      |                                                                                                                                                          |
| 2.2.2.                                                                                                                   | T.M.D.S. Link Usage                                                                                                                                                                                                                   |                                                                                                                                                          |
| 2.2.3.                                                                                                                   | Model High Color Depth Support                                                                                                                                                                                                        | ........................................................................11 ...........................................................................13 |
| 2.2.4.                                                                                                                   | Pixel Format Support...........................................................................14                                                                                                                                     |                                                                                                                                                          |
|                                                                                                                          | Low                                                                                                                                                                                                                                   |                                                                                                                                                          |
| 2.2.5.                                                                                                                   | EDID............................................................................................................14 DDC.............................................................................................................15 |                                                                                                                                                          |
| 2.2.6.                                                                                                                   |                                                                                                                                                                                                                                       |                                                                                                                                                          |
| 2.2.7. 2.2.8.                                                                                                            | Gamma........................................................................................................15                                                                                                                       | Scaling.........................................................................................................15                                       |
| 2.2.9. 2.2.10.                                                                                                           | Hot Plugging................................................................................................16                                                                                                                        | Required..................................................17                                                                                             |
|                                                                                                                          | HSync, VSync and Data Enable                                                                                                                                                                                                          |                                                                                                                                                          |
| 2.2.11.                                                                                                                  | Data Formats...............................................................................................18                                                                                                                         |                                                                                                                                                          |
| 2.2.12.                                                                                                                  | Interoperability with Other T.M.D.S. Based Specifications                                                                                                                                                                             | .........................18                                                                                                                              |
| 2.3.                                                                                                                     | Bandwidth ................................ ................................                                                                                                                                                           | ................................ .......18 ..................................................................18                                          |
| 2.3.1. 2.3.2.                                                                                                            | Minimum Frequency Supported Alternate Media                                                                                                                                                                                           | ...........................................................................................19                                                            |
| 2.4.                                                                                                                     | Digital Monitor Power Management................................                                                                                                                                                                      | ................................19                                                                                                                       |
| 2.4.1.                                                                                                                   | Link Inactivity Definition...............................................................................21                                                                                                                           |                                                                                                                                                          |
| 2.4.2.                                                                                                                   | System Power Management Requirements................................................21                                                                                                                                                |                                                                                                                                                          |
| 2.4.3. 2.5.                                                                                                              | Monitor Power Management Requirements................................................21 Analog................................ ................................                                                                       | ................................ .............22                                                                                                         |
| 2.5.1.                                                                                                                   | Analog Signal Quality ..................................................................................22                                                                                                                            |                                                                                                                                                          |
| 2.5.2.                                                                                                                   | HSync and VSync Required........................................................................22                                                                                                                                    |                                                                                                                                                          |
| 2.5.3.                                                                                                                   | Analog Timings............................................................................................22                                                                                                                          |                                                                                                                                                          |
| 2.5.4.                                                                                                                   | Management........................................................................23                                                                                                                                                  |                                                                                                                                                          |
|                                                                                                                          | Analog Power                                                                                                                                                                                                                          |                                                                                                                                                          |
| 2.6.                                                                                                                     | Signal List................................ ................................                                                                                                                                                          | ................................ ........23                                                                                                              |
| 3.                                                                                                                       | T.M.D.S. Protocol Specification.............................................................24                                                                                                                                        |                                                                                                                                                          |
|                                                                                                                          | Overview ................................                                                                                                                                                                                             | ................................ ................................ .........24                                                                            |
| 3.1 3.1.1 3.1.2                                                                                                          | Link Architecture..........................................................................................24                                                                                                                         | Clocking.......................................................................................................24                                        |
| 3.1.3                                                                                                                    | Synchronization...........................................................................................25                                                                                                                          |                                                                                                                                                          |
| 3.1.4                                                                                                                    | Encoding......................................................................................................25                                                                                                                      |                                                                                                                                                          |
| 3.1.5                                                                                                                    | Dual-Link Architecture.................................................................................25                                                                                                                             |                                                                                                                                                          |
|                                                                                                                          | ................................                                                                                                                                                                                                      | ................................                                                                                                                         |
| 3.2 3.2.1                                                                                                                | Encoder Specification Channel Mapping                                                                                                                                                                                                 | .....................26 ........................................................................................26                                       |

| 3.2.2                                                                                                       | Encode Algorithm                                                                                                                                                      | ........................................................................................28        |
|-------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|
| 3.2.3                                                                                                       | Serialization .................................................................................................30                                                     |                                                                                                   |
| 3.3                                                                                                         | Decoder Specification                                                                                                                                                 | .....................................................................................30           |
| 3.3.1                                                                                                       | Clock Recovery............................................................................................30                                                          |                                                                                                   |
| 3.3.2                                                                                                       | Data Synchronization...................................................................................30                                                             |                                                                                                   |
| 3.3.3                                                                                                       | Decode Algorithm                                                                                                                                                      | ........................................................................................31        |
| 3.3.4                                                                                                       | Channel Mapping.........................................................................................31                                                            |                                                                                                   |
| 3.3.5                                                                                                       | Error Handling..............................................................................................31                                                        |                                                                                                   |
| 3.4                                                                                                         | Link Timing Requirements                                                                                                                                              | ..............................................................................32                  |
| 4.                                                                                                          | T.M.D.S. Electrical Specification............................................................33                                                                       |                                                                                                   |
| 4.1.                                                                                                        | Overview..........................................................................................................33                                                  |                                                                                                   |
| 4.2.                                                                                                        | System Ratings and Operating Conditions                                                                                                                               | .....................................................35                                           |
| 4.3.                                                                                                        | Transmitter Electrical Specifications                                                                                                                                 | ...............................................................35                                 |
| 4.4.                                                                                                        | Receiver Electrical Specifications                                                                                                                                    | ...................................................................38                             |
| 4.5.                                                                                                        | Cable Assembly Specifications                                                                                                                                         | .......................................................................39                         |
| 4.6.                                                                                                        | Jitter Specifications .........................................................................................39                                                     |                                                                                                   |
| 4.7.                                                                                                        | Electrical Measurement Procedures                                                                                                                                     | ...............................................................40                                 |
| 4.7.1.                                                                                                      | Test Patterns                                                                                                                                                         | ...............................................................................................40 |
| 4.7.2.                                                                                                      | Normalized Amplitudes................................................................................40                                                               |                                                                                                   |
| 4.7.3.                                                                                                      | Clock Recovery............................................................................................40                                                          |                                                                                                   |
| 4.7.4.                                                                                                      | Transmitter Rise/Fall                                                                                                                                                 | Time...........................................................................41                 |
| 4.7.5.                                                                                                      | Transmitter Skew Measurement..................................................................41                                                                      |                                                                                                   |
| 4.7.6.                                                                                                      | Transmitter Eye                                                                                                                                                       | ...........................................................................................41     |
| 4.7.7.                                                                                                      | Jitter Measurement......................................................................................42                                                            |                                                                                                   |
| 4.7.8.                                                                                                      | Receiver Eye                                                                                                                                                          | ...............................................................................................42 |
| 4.7.9.                                                                                                      | Receiver Skew Measurement......................................................................42                                                                     |                                                                                                   |
| 4.7.10.                                                                                                     | Differential TDR Measurement Procedure                                                                                                                                | ..................................................42                                              |
| 5.                                                                                                          | Physical Interconnect Specification......................................................43                                                                           |                                                                                                   |
| 5.1.                                                                                                        | Overview..........................................................................................................43                                                  |                                                                                                   |
| 5.2.                                                                                                        | Mechanical Characteristics                                                                                                                                            | .............................................................................43                   |
| 5.2.1.                                                                                                      | Signal Pin Assignments...............................................................................43                                                               |                                                                                                   |
| 5.2.2.                                                                                                      | Contact Sequence.......................................................................................44                                                             |                                                                                                   |
| 5.2.3.                                                                                                      | Digital-Only Receptacle                                                                                                                                               | Connectors............................................................45                          |
| 5.2.4.                                                                                                      | Combined Analog and Digital Receptacle Connectors                                                                                                                     | ...............................46                                                                 |
| 5.2.5.                                                                                                      | Digital Plug Connectors                                                                                                                                               | ...............................................................................47                 |
| 5.2.6.                                                                                                      | Analog Plug Connectors..............................................................................47                                                                |                                                                                                   |
| 5.2.7.                                                                                                      | Recommended Panel Cutout                                                                                                                                              | ......................................................................48                          |
| 5.2.8.                                                                                                      | Mechanical Performance.............................................................................49                                                                 |                                                                                                   |
| 5.3.                                                                                                        | Electrical Characteristics.................................................................................50                                                         |                                                                                                   |
| 5.3.1.                                                                                                      | Connector Electrical Performance...............................................................50                                                                     |                                                                                                   |
| 5.3.2.                                                                                                      | Cable Electrical Performance......................................................................52                                                                  |                                                                                                   |
| 5.4.                                                                                                        | Environmental Characteristics                                                                                                                                         | ........................................................................53                        |
| 5.5.                                                                                                        | Test Sequences ..............................................................................................54                                                       |                                                                                                   |
| 5.5.1.                                                                                                      | Group 1: Mated Environmental....................................................................54                                                                    |                                                                                                   |
| 5.5.2.                                                                                                      | Group II: Mated Mechanical                                                                                                                                            |                                                                                                   |
| 5.5.3.                                                                                                      | ........................................................................55 Group III: Mechanical Mate/Unmate Forces................................................56 |                                                                                                   |
| 5.5.4.                                                                                                      | Group IV: Insulator Integrity.........................................................................57                                                              |                                                                                                   |
| 5.5.5.                                                                                                      | Group V: Cable Flexing                                                                                                                                                | ...............................................................................58                 |
| 5.5.6.                                                                                                      | Group VI: Electrostatic Discharge                                                                                                                                     | ...............................................................58                                 |
| Appendix A. Glossary of Terms............................................................................59 | Appendix A. Glossary of Terms............................................................................59                                                           |                                                                                                   |
| Appendix B. Contact Geometry ........................................................................61     | Appendix B. Contact Geometry ........................................................................61                                                               |                                                                                                   |
| Appendix C. Digital                                                                                         | Monitor Power State - State                                                                                                                                           | Diagram..............................76                                                           |

## 1. Introduction

The Digital Visual Interface (hereinafter DVI) specification provides a high-speed digital connection for visual data types that is display technology independent.  The interface is primarily focused at providing a connection between a computer and its display device.  The DVI specification meets the needs of all segments of the PC industry (workstation, desktop, laptop, etc) and will enable these different segments to unite around one monitor interface specification.

The DVI interface enables:

1. Content to remain in the lossless digital domain from creation to consumption
2. Display technology independence
3. Plug and play through hot plug detection, EDID and DDC2B
4. Digital and Analog support in a single connector

This interface specification is organized as follows:

- ¤ Chapter 1 provides motivation, scope, and direction of the specification.
- ¤ Chapter 2 provides a technical overview and the specific system and display architectural and programming requirements that must be met in order to create an inter-operable context for the DVI interface.
- ¤ Chapter 3 provides a detailed description of the transition minimized differential signaling (hereinafter T.M.D.S.) protocol and encoding algorithm.
- ¤ Chapter 4 provides a detailed description of the electrical requirements of T.M.D.S..
- ¤ Appendix A is a glossary.
- ¤ Chapter 5 contains the connector mechanical description and the electrical characteristics of the connector, including signal placement.
- ¤ Appendix B details the connector contact geometry
- ¤ Appendix C enlarged digital monitor power state diagram

## 1.1. Scope and Motivation

The purpose of this interface specification is to provide an industry specification for a digital interface between a personal computing device and a display device.  This specification provides for a simple low-cost implementation on both the host and monitor while allowing for monitor manufacturers and system providers to add feature rich values as appropriate for their specific application.

The DDWG has worked to address the various business models and requirements of the industry by delivering a transition methodology that addresses the needs of those various requirements.  This is accomplished by specifying two connectors with identical mechanical characteristics: one that is digital only and one that is digital and analog.  The combined digital and analog connector is designed to meet the needs of systems with special form factor or performance requirements.  Having support for the analog and digital interfaces for the computer to monitor interconnect will allow the end user to simply plug the display into the DVI connector regardless of the display technology.

The digital only DVI connector is designed to coexist with the standard VGA connector. With the combined connector or the digital only connector the opportunity exists for the removal of the legacy VGA connector.  The removal of the legacy VGA connector is anticipated to be driven strictly by business demands.

A digital interface for the computer to monitor interconnect has several benefits over the standard VGA connector.  A digital interface ensures all content transferred over this interface

remains in the lossless digital domain from creation to consumption.  The digital interface is developed with no assumption made as to the attached display technology.

This specification completely describes the interface so that one could implement a complete transmission and interconnect solution or any portion of the interface.  The T.M.D.S. protocol and associated electrical signaling as developed by Silicon Image is described in detail.  The mechanical specification of the connector and the signal placement within the connector are described.

A device that is compliant with this specification is should be interoperable with other compliant devices through the plug and play configuration and implementation provided for in this specification.  The plug and play interface provides for hot plug detection and monitor feature detection. Additionally, this specification describes the number of T.M.D.S. links available to the display device and the method for configuring the T.M.D.S. links.

The bandwidth and pixel formats that are anticipated and supported by this specification are described.  This specification describes the signal quality characteristics required by the cable to support the high data rates required by large pixel format displays.  Additionally the DVI specification provides for alternate media implementations.  Power management and plug and play configuration management are both fully described.  To ensure baseline functionality, low-pixel format requirements are included.

As appropriate, this interface makes use of existing VESA specifications to allow for simple low-cost implementations.  Specifically VESA Extended Display Identification Data (EDID) and Display Data Channel (DDC) specifications are referenced for monitor identification and the VESA Monitor Timing Specification (DMT) is referenced for the monitor timings.

## 1.2. Performance Scalability

The amount of raw bandwidth that is required to support a display type is technology specific. For example a typical CRT allocates a blanking interval time.  This blanking interval requirement is technology specific and forces the data transfer to occur in a limited time slot. This limited time slot increases the bandwidth requirement of the data active window while mandating long data inactive time periods to allow for the blanking to complete.  A blanking period is display technology specific and should not be forced on all display types.  Reduced blanking periods provide more of the actual interconnect bandwidth to the display device.  It is anticipated that display technology will continue to advance such that blanking period overheads will be decreased and will eventually be eliminated thus providing the maximum bandwidth of the interface to the display device.  As displays advance even beyond the capabilities of the copper physical layer it is anticipated display interfaces will migrate toward providing only changed data to the display.  This limited update architecture is an expectation only, not a requirement.

Figure 1-1. Available Link Bandwidth

Figure 1-1. Available Link Bandwidth. represents the raw bandwidth available from each T.M.D.S. link.  The three horizontal axes across the bottom of the figure represent the different overhead requirements of the various display technologies.  To determine the number of links required for a specific application simply use the legend on the right to select the pixel format, then find the pixel format on the horizontal axis that represents the display technology of interest.  Once the pixel format has been identified draw a vertical line to intersect the T.M.D.S. bandwidth curve, this is the bandwidth required for the pixel format and display technology selected.

## 1.2.1. Bandwidth Estimation

The bandwidth that is required over a physical medium is easy to estimate.  Data required as input are Horizontal Pixels, Vertical Pixels, Refresh Frequency (Hz), Bandwidth Overhead (loosely defined as blanking).  An equation to quickly estimate the bandwidth required is:

<!-- formula-not-decoded -->

Equation 1-1.  Pixels per Second.

Where overhead is defined as

<!-- formula-not-decoded -->

Equation 1-2. Overhead.

To measure the link bandwidth in pixels per second assumes each of the three channels is transmitting an R-pel, G-pel, and B-pel data in unison.

A pel is a pixel element, i.e. the singular red value or green value or blue value of an RGB pixel.  Pixels per second can be converted to bits per second by multiplying the pixels per second value by the number of bits per pixel.  Using Equation 1-1 and the T.M.D.S. signaling protocol, pixels per second equals the T.M.D.S. clock link frequency.

## 1.2.2. Conversion to Selective Refresh

It is anticipated that in the future the refreshing of the screen will become a function of the monitor.  Only when data has changed will the data be sent to the monitor.  A monitor would have to employ an addressable memory space to enable this feature.  With a selective refresh interface, the high refresh rates required to keep a monitor ergonomically pleasing can be maintained while not requiring an artificially high data rate between the graphics controller and the monitor. The DVI specification does nothing to preclude this potential migration.

## 1.3. Related Documents

The DVI specification references other VESA specifications to enable low cost implementations.  Additionally, the DVI specification references the VESA specifications to help enable plug and play interoperability.

## 1.3.1. VESA Display Data Channel (DDC) Specification

This specification incorporates a subset of the Display Data Channel for operation between a DDC compliant host and DDC compliant monitor.  The DDC level support required in this specification is DDC2B. Compatibility with earlier DDC versions is not supported.  It is anticipated that the DVI specification will require support for the Enhanced-DDC specification within 12 months of VESA adoption.  Refer to VESA DDC Specification Version 3.0 for more information.

## 1.3.2. VESA Extended Display Identification Data (EDID) Specification

Both DVI compliant systems and monitors must support the EDID data structure.  EDID 1.2 and 2.0 are recommended for interim support for systems.  Complete requirements are detailed in section 2.2.5.  The system is required to read the EDID data structure to determine the capabilities supported by the monitor.  It is anticipated that the DVI specification will require support for the EDID 1.3 data structure support within 12 months of VESA adoption. Refer to VESA EDID Specification Version 3.0 for more information.

## 1.3.3. VESA Video Signal Standard (VSIS) Specification

Systems implementing the analog portion of the DVI specification must be in compliance with the VESA VSIS specification within 12 months of VESA adoption.  Refer to VESA VSIS Specification Version 1.6p for more information.

## 1.3.4. VESA Monitor Timing Specifications (DMT)

Systems implementing the analog portion of the DVI specification should be in compliance with the VESA and Industry Standards and Guidelines for Computer Display Monitor Timings specification.  Refer to VESA and Industry Standards and Guidelines for Computer Display Monitor Timings Version 1.0 Revision 0.8 for more information

## 1.3.5. VESA Generalized Timing Formula Specification (GTF)

Systems implementing the analog portion of the DVI specification should be in compliance with the VESA Generalized Timing Formula Specification.  Refer to VESA Generalized Timing Formula Specification Version 1.0 Revision 1.0 for more information.

## 1.3.6. VESA Timing Definition for LCD Monitors Specification

LCD monitors should be in compliance with the VESA Timing Definition for LCD Monitor Specification.  Refer to VESA Timing Definition for LCD Monitor Specification Version 1 Draft 8 for more information.

## 1.3.7. Compatibility with Other T.M.D.S. Based Implementations.

The DVI specification is based on a T.M.D.S. electrical layer.  Every effort has been made to ensure interoperability with existing products that support similar T.M.D.S. signaling. Implementations of VESA DFP or VESA P&amp;D specification should connect to the DVI specified connector through a simple adapter.

## 2.  Architectural Requirements

## 2.1. T.M.D.S. Overview

The Digital Visual Interface uses transition minimized differential signaling for the base electrical interconnection.  The T.M.D.S. link is used to send graphics data to the monitor. The transition minimization is achieved by implementing an advanced encoding algorithm that converts 8 bits of data into a 10-bit transition minimized, DC balanced character.

This interface specification allows for two T.M.D.S. links enabling large pixel format digital display devices, see Figure 2-1.  One or two T.M.D.S. links are available depending on the pixel format and timings desired.  The two T.M.D.S. links share the same clock allowing the bandwidth to be evenly divided between the two links.  As the capabilities of the monitor are determined the system will choose to enable one or both T.M.D.S. links.

Figure 2-1. T.M.D.S. Logical Links

The transmitter incorporates an advanced coding algorithm to enable T.M.D.S. signaling for reduced EMI across copper cables and DC-balancing for data transmission over fiber optic cables.  In addition, the advanced coding algorithm enables robust clock recovery at the receiver to achieve high-skew tolerance for driving longer cable lengths as well as shorter low cost cables.

## 2.2. Plug and Play Specification

## 2.2.1. Overview

On initial system boot a VGA compliant device might be assumed by the graphics controller. To accommodate system boot modes and debug modes, the DVI compliant monitor must support the low pixel format mode defined in section 2.2.4.2.  Both BIOS POST and the operating system are likely to query the monitor using the DDC2B protocol to determine what pixel formats and interface is supported.  DVI makes use of the EDID data structure for the identification of the monitor type and capabilities.  The combination of pixel formats supported by the monitor, pixel formats supported by the graphics subsystem, and user input will determine what pixel format to display.

DVI provides for single or dual T.M.D.S. link implementations.  The single link can support greater than high definition television (HDTV) pixel formats at a reduced blanking interval. The dual link configuration is intended to provide support for the higher bandwidth demands of displays that do not support reduced blanking.  The dual link configuration will enable support for large pixel format digital CRTs; the dual link is not limited to large pixel format digital CRT support.  Digital CRTs are envisioned to be similar to classical CRTs except the graphical data received by the display transducer is in the digital domain with the final digital to analog conversion occurring in the monitor.  Digital CRTs require time to be allocated to horizontal and vertical retrace intervals.  For a CRT to display the same pixel format as a reduced blanking Flat Panel monitor, the retrace time allocation places a high peak bandwidth requirement on the graphics subsystem.  The higher bandwidth requirement of the digital CRTs is achieved by using two T.M.D.S. links.  With the use of the second link and today' s technology transmitter, a digital CRT that is compliant with VESA's Generalized Timing Formula (GTF) can support pixel formats of greater than 2.75 million pixels at an 85Hz refresh rate.  A display device that supports reduced blankings and refresh rates can easily support more than 5 million pixels with two T.M.D.S. links.

On initial system boot, if a digital monitor is detected, only the primary T.M.D.S. link can be activated.  The secondary T.M.D.S. link can become active after the graphics controller driver has determined the capability for the second link exists in the monitor.  The two T.M.D.S. links share the same clock allowing the bandwidth to be evenly divided between the two links.  If an analog DVI compliant monitor is attached to the system, the system should treat the analog DVI compliant monitor as it would a analog monitor connected to the 15 pin VGA connector.

If the DVI compliant monitor was not present during the boot process, the Hot Plug Detection mechanism exists to allow the system to determine when a DVI compliant monitor has been plugged in.  After the Hot Plug-In event the system will query the monitor using the DDC2B interface and enable the T.M.D.S. link if required.

After the pixel format and timings have been determined there are two more parameters that effect the user perception of the picture quality, gamma and scaling.

The gamma characteristic of a monitor is display technology dependent.  In the past a CRT has been assumed as the primary display technology to be used.  To ensure display independence, no assumption is made of display technology.  The DVI requires a gamma characteristic of the data at the interface allowing monitors of varying display technologies to compensate for their specific display transfer characteristic.

If the monitor is identified in the EDID data structure as a fixed pixel format device that supports more than a single pixel format, then a monitor scalar is assumed to exist.  A monitor scalar allows monitor vendors the ability to ensure the quality of the displayed image.  For complete details on Scaling and EDID requirement please see their respective sections later in this specification.

## 2.2.2. T.M.D.S. Link Usage Model

To maintain compatibility with EDID data structure the DVI must be able to select between one or two links based solely on the pixel format and timing information.  The compatibility of a monitor and system must be easily identified by the system and reported to the user.  To ensure identical pixel formats are supported in an identical fashion by the host and the monitor, the T.M.D.S. link #0 must be used to support all pixel formats and timings requiring up to and including 165MHz.  Any pixel format and blanking interval requiring more than a 165MHz-clock frequency must be supported using two T.M.D.S. links.  If a pixel format and timing requiring greater than 165MHz-clock is supported, each T.M.D.S. link must operate at

half the frequency required to support the pixel format and timing.  For example, if a pixel format and timing requiring a 200MHz pixel clock is supported, then both links must operate at 100MHz.  One link at 165MHz and the second link at 30MHz is not allowed.  As such, the second links minimum operating frequency is 82.5MHz.

Note:  It is perfectly acceptable for a single link to have a maximum operating frequency of less than 165 MHz.  For example a system desiring to support a maximum pixel format of 800x600 at 60 Hz refresh using VESA's defined timings would only need to implement a link speed of 40 MHz.  If a monitor that supported multiple higher pixel formats were attached then pixel formats up to greatest common dominator (800x600) could be used.

The system is required to manage the limitations of the graphics controller, transmitter, and monitor.  The user should not be able to select a pixel format greater than can be supported by the least capable component in the graphics subsystem.

## Crossover Frequency Architectural Note:

The goal of the cross over frequency is to ensure both the system and the monitor support any specific pixel format using the same number of links.  For example, if no single crossover frequency existed and a monitor supported 1600x1200 at 60 Hz refresh using VESA's defined timings the monitor might choose to implement the required 162 MHz link as two 81 MHz links.  If a system supported the same pixel format and timings but using only one 162 MHz link then an incompatibility has been created.  The system and monitor would both support the same exact pixel format and timing but the combination would not be able to support the pixel format.  Prior to booting the system (at purchase time), no indication would be available to a user to determine if the monitor and system could interoperate.  With no defined crossover frequency, it would take individuals with intimate knowledge of the design of both the graphics solution and the monitor to determine if a specific pixel format could be supported.

Table 2-1. Single and Dual Link Operation.

| System              | Single Link Note #1                        | Dual Link                               |
|---------------------|--------------------------------------------|-----------------------------------------|
| Single Link Note #1 | OK                                         | OK; Monitor at low pixel format Note #2 |
| Dual Link           | OK; System pixel format limited by monitor | OK                                      |

Table 2-1 identifies the potential T.M.D.S. link combinations of monitors and system.  The monitor T.M.D.S. link possibilities are represented across the top row.  The system T.M.D.S. link possibilities are represented down the left-hand column.

During the boot process, when the graphics subsystem is initialized only T.M.D.S. link (link #0) will be active.  T.M.D.S. link #1 can become active only after the graphics subsystem determines a pixel format and timing requiring more than 165MHz T.M.D.S. clock is supported by the system and monitor and the pixel format has been requested by the user.

Note #1.  In single link implementations the link must be limited to 165MHz T.M.D.S clock or less operation. Additionally, the first link of a dual link implementation must support

165MHz T.M.D.S. clock operation.  The single link only mode must be used for 25MHz to 165MHz T.M.D.S clock operation and the first link can operate at above 165MHz T.M.D.S clock only in the case of the total bandwidth requirement surpassing 330MHz T.M.D.S clock.

Note #2.  The two-link monitor plugged into the one link system still boots and displays images.  The images are pixel format limited by the graphics driver to the maximum system single link frequency of up to 165MHz T.M.D.S clock operation.  A configuration utility may optionally report to the user the nature of the system limitations.  A message only stating there is a system limitation is OK, ideally a message should be displayed by the operating system or a display utility to inform the user specifically the issue is the graphics sub-system does not support the larger pixel format.

## 2.2.2.1. T.M.D.S. Link System Requirements

A DVI compliant system must implement a minimum of a single T.M.D.S. link, link  #0.  The minimum low pixel format mode must be supported.  The maximum pixel format supported is implementation specific.  If the system supports pixel formats and timings that require greater than a 165MHz T.M.D.S. clock then implementation of the second T.M.D.S. link is required. There is no specified maximum for the dual link implementations.

A system supporting dual T.M.D.S. links must be able to dynamically switch between supported pixel formats including switching between pixel formats that require single and dual link configurations.  When a dual T.M.D.S. link capable system is driving only a single link, the secondary link must be inactive.

## 2.2.2.2. T.M.D.S. Link Monitor Requirements

A DVI compliant monitor must implement a minimum of a single T.M.D.S. link, link #0. The minimum low pixel format mode must be supported.  The maximum pixel format supported is implementation specific.  If the monitor supports pixel formats and timings that require greater than a 165MHz T.M.D.S. clock then implementation of the second T.M.D.S. link is required.

A dual link T.M.D.S. monitor must be able to detect the activity of each link and dynamically switch between supported pixel formats including switching between pixel formats that require single and dual link configurations.

## 2.2.3. High Color Depth Support

Color depths requiring greater than 24-bit per pixel are allowed to be supported via the second link.  Future versions of this specification reserve the right to require different implementations of high color depth support that are not backwards compatible with this version of the specification.

The colors per pel are logically concatenated with the most significant bits provided over the primary T.M.D.S. link (link #0) and the least significant bits provided over the secondary T.M.D.S. link (link #1).  If implemented, the data format on the secondary T.M.D.S. links must the same 24-bit MSB aligned RGB TFT data format as defined for the primary link.

The system must identify the capability exists in the monitor before the high color depth is enabled.  If the monitor does not support the high color depth, the system must be able to operate in the required 24-bit format.

## 2.2.4. Low Pixel Format Support

Low-pixel format modes are supported to allow a default operation mode.  This default operation mode enables the user to view a legible display of BIOS messages and progress as well as Operating System initial loading messages.  A legible picture does not require the image to be scaled to full screen or centered.

Once the Operating System loads the graphics controller driver the driver may switch into a different pixel format and timing mode.  The video BIOS is required to respond to all legacy VESA BIOS calls and INT 10 BIOS (IBM PS/2 Legacy BIOS) calls, however it is acceptable for the hardware to emulate the legacy mode.

## 2.2.4.1. System Low Pixel Format Support Requirement

Industry Standard Timings for 640x480 pixel format at 60 Hz Refresh with a pixel clock of 25.175 MHz and Horizontal Frequency of 31.5 kHz.

To insure compatibility the system must re-map int10 mode 3 BIOS calls to required low pixel format support mode.

## 2.2.4.2. Monitor Low Pixel Format Support Requirement

Industry Standard Timings for 640x480 pixel format at 60 Hz Refresh with a pixel clock of 25.175 MHz and Horizontal Frequency of 31.5 kHz.

## 2.2.5. EDID

At the time of the creation of the DVI specification there is a development effort underway by VESA, the standards body responsible for the creation of monitor identification standards. The EDID 1.3 data structure specification that is under development purportedly addresses several of the display technology independent issues germane to the DVI specification.  It is anticipated that the DVI specification will require support for the EDID 1.3 data structure support within 12 months of VESA adoption.

## 2.2.5.1. EDID System Requirements

A DVI compliant system must support the EDID data structure.  EDID 1.2 and 2.0 are recommended for interim support for systems.  No assumption above the low pixel format requirement (640x480) pixel format can be made about monitor support.  The system is required to read the EDID data structure to determine the capabilities supported by the monitor.

Current digital monitors based on the T.M.D.S. electrical specification use both the EDID 1.2 data structure and the EDID 2.0 data structure.  Any system desiring to support both groups of existing monitors must support both EDID data structures.

## 2.2.5.2. EDID Monitor Requirements

A DVI compliant monitor must support the EDID data structure.  EDID 1.2 and 2.0 are recommended for interim support for systems.  The DVI low-pixel format requirement does not have to be listed in the EDID data structure but the monitor must present a legible image. If the monitor is a fixed pixel format monitor then the EDID "Preferred Timing Mode" bit

must be set (EDID 1.2 data structure offset 18h bit 1; EDID 2.0 data structure offset 7Eh bit 6) and the native pixel format of the monitor must be reported in the first detailed timing field.

## 2.2.6.  DDC

## 2.2.6.1. System DDC Requirements

DDC2B support is required.  The DDC +5 volt signal is required in a DVI compliant system.

Note: The power pin must be able to supply a minimum of 55 mA and the monitor may not draw more than 50 mA.

## 2.2.6.2. Monitor DDC Requirements

DDC2B support is required.  A DVI compliant monitor is not allowed to issue DDC1 transactions.  Within 250 mS of the application of the DDC required +5 volt, the monitor must be able to respond to transactions to the EDID data structure by DDC2B.

Note: The DDC required +5 volt power pin must be able to supply a minimum of 55 mA.  If the monitor is powered off, the monitor may not draw more than 50 mA.  If the monitor is powered on, the monitor may not draw more than 10 mA.

## 2.2.7.  Gamma

The term "gamma" is frequently misused; for an excellent description of the term and its usage please refer to the sRGB specification which can be found at http://www.srgb.com/.  By way of summary, CRT monitors (and TV displays) have an inherently non-linear color transfer function, requiring pre-compensation of input data in order to generate a normalized image.  However, computer generated graphical data (spreadsheets, word processor documents, etc) are generated in a mathematically linear color space.  Since this data is typically displayed on a CRT device, the graphics controller applies a display transfer function known as gamma correction, to pre-compensate the data as it leaves the graphics controller.  The typical CRT display transfer functions are represented by an exponential function of the form Y=x γ , where x is the input signal, Y the output signal and γ (gamma) is the display transfer characteristic, which is approximately 2.2 for CRT's.

Generating accurate color renditions between different types of output devices is an ongoing research and development topic in the industry.  Standards bodies, including the International Color Consortium, are working to standardize approaches.  It is, therefore, beyond the intent and scope of this specification to define standards in this area.

However, pending further definitive requirements, it is recommended as a default position, that digital monitors of all types support a color transfer function similar to analog CRT monitors ( γ = 2.2 ) which make up the majority of the computer display market.  This will avoid, to a great extent, poor color representations on digital monitors, and the necessity of graphics controllers supporting alternate transfer functions.

## 2.2.8. Scaling

Fixed pixel format (i.e. spatially sampled) monitors have two basic modes of operation, 1.display of native pixel format data and 2. display of data scaled to the native pixel format of the monitor.  Scaling to the native pixel format is the responsibility of the monitor.  It is presumed a quality scalar is a value-added feature for the monitor.  Fixed pixel format digital

monitors should make every effort to provide a quality scalar thus allowing the end-user experience to match that of the typical analog multi-sync monitors.

## 2.2.8.1. System Scaling Requirements

The host may assume that the monitor can display the required low pixel format mode even if it is not listed in the EDID data structure.  If the monitor does not support a requested pixel format, then the graphics controller may 1. scale the image to the monitor' s native pixel format, 2. center the image or 3. report the pixel format as unavailable.  The system may provide a utility to allow the end user to select between the monitor scalar, if it exists, and the system scalar.  The default mode of operation is to use the monitor' s scalar when available.

Note:  To eliminate the potential for cascaded scalars, if the system scales the image then the system must scale the image to the monitor's defined preferred mode timing (native pixel format in a fixed pixel format panel).

## 2.2.8.2. Monitor Scaling Requirements

If the monitor is identified as a fixed pixel format device that supports more than a single pixel format, a monitor scalar is required to exist for those supported pixel formats, and should always be used.  The monitor should scale to all standard pixel formats between its maximum pixel format and the low pixel format requirement.  The monitor must only claim support, in the EDID data structure, for a pixel format that can be displayed full screen in at least one dimension.

If the monitor does not have a scalar, the monitor must only report its single fixed pixel format in the EDID data, but the monitor must still present a legible picture when presented with the required low-pixel format mode.

Note: If a DVI compliant monitor only supports (i.e. full screen in at least one direction) its native, fixed pixel format and if the required low pixel format mode is a legible but not full screen display, then the monitor must only list support for its native, fixed pixel format in the EDID data structure.  If the required low pixel format mode is displayed full screen in at least one dimension, it can be listed in EDID.

Note: If the monitor is a fixed pixel format monitor then the EDID "Preferred Timing Mode" bit must be set and the native pixel format of the monitor must be reported in the first detailed timing field. (EDID "Preferred Timing Mode" bit is located in EDID 1.2 data structure at offset 18h bit 1 and in EDID 2.0 data structure offset 7Eh bit 6d)  This preferred mode timing identification requirement is designed to allow the system to determine the native pixel format of a flat panel display (by design, a fixed pixel format device).

## 2.2.9. Hot Plugging

Hot Plug Detection (HPD) is a system level function requiring industry specifications at both hardware and software levels.  It is beyond the scope of this specification to define a complete system solution.  This section is therefore limited to the specification of the hot plug signal that provides the hardware underpinning for a complete system solution.  The operation of the hot plug pin, as described below, is required by this specification. Any specific system response to the hot plug pin is optional.

Future software specifications are anticipated, which should provide the complete system solution.  In the interim, the graphics driver is free to generate its own application based on the hot plug signal.

Hot Plug Events

Monitor Attachment : When a "Monitor Attach" Hot Plug event is detected the graphics subsystem must generate a system level event (OS dependent) to allow the operating system to read the monitor' s EDID data.  If the graphics subsystem and monitor support compatible pixel formats the operating system should enable the monitor and the T.M.D.S. link if required.

Monitor Removal : When a "Monitor Removal" Hot Plug event is detected the graphics subsystem must generate a system level event (OS dependent) to notify the operating system of the event.  Additionally, if the DVI complaint monitor is a digital monitor, when "Monitor Removal" is detected the graphics subsystem must disable the T.M.D.S. transmitter within 1 second.

## 2.2.9.1. System Hot Plugging Requirements

Any specific system response to Hot Plug Detection is future OS dependent.  It is anticipated this functionality will be required in the future, as Operating System API' s become available to take advantage of this feature.

When the host detects a transition above +2.0 volts or below +0.8 volts the graphics subsystem must generate a system level event (OS dependent) to inform the Operating System of the event. Additionally, if the DVI complaint monitor is a digital monitor, when "Monitor Removal" is detected the graphics subsystem must disable the T.M.D.S. transmitter within 1 second.

Note: The VESA Plug and Display specification allows for up to +20 volts to be applied to its Charge/Hot Plug Detect Pin, although no such implementations are known to exist.  To ensure the safety of the transmitter and to enable compatibility with a P&amp;D monitor, it is required that any adapter connecting a P&amp;D monitor to a DVI compliant system leaves the HPD pin unconnected, or otherwise insures that +5 volts is not exceeded.  +20 volt tolerance is not required of a DVI compliant host.

## 2.2.9.2. Monitor Hot Plugging Requirements

The monitor must provide a voltage of greater than +2.4 volts on the Hot Plug Detect (HPD) pin of the connector only when the EDID data structure is available to be read by the host. When the EDID data structure can not be read then voltage on the HPD pin must be below +0.4 volts.

Implementation Note: As an example for hot plug support, a simple monitor implementation of HPD support could be a pull up resistor to the EDID power supply.

## 2.2.10. HSync, VSync and Data Enable Required

It is expected that digital CRT monitors will become available to connect to the DVI interface. To ensure display independence, the digital host is required to separately encode HSync and VSync in the T.M.D.S. channel.

The digital host is required to encode Data Enable (hereinafter DE) in the T.M.D.S. channel. DE must be an active high signal.

Note: The bit mapping within the T.M.D.S. is specified in section 3.2.

## 2.2.11.  Data Formats

## 2.2.11.1. System Data Format Support

The system must support the 24-bit MSB aligned RGB TFT data format as a minimum.  The 24-bit MSB aligned RGB TFT data format is defined in the VESA EDID specification version 3.0.  Note that lower color depths are also defined there.

If the monitor implements the EDID 1.2 data structure the system must assume the monitor supports the 24-bit MSB aligned RGB TFT data format.

## 2.2.11.2. Monitor Data Format Support

If the monitor chooses to implement the EDID 1.2 data structure then the monitor must accept the 24-bit MSB aligned RGB TFT data format as defined in the VESA EDID specification version 3.0.

If the monitor implements the EDID 2.0, 1.3 or newer data structure the monitor may specify any data format that is definable within the EDID data structure used.  In all cases the monitor must support the 24-bit MSB aligned RGB TFT data format as a minimum.

## 2.2.12. Interoperability with Other T.M.D.S. Based Specifications

The DVI specification is based on a T.M.D.S. electrical layer.  Every effort has been made to ensure interoperability with existing products that support similar T.M.D.S. signaling.  DC coupled implementations of VESA DFP or VESA P&amp;D specification should connect to the DVI specification through a cable adapter.

While every effort is being made to ensure the interoperability of the T.M.D.S. link, the accessory functions available in other specifications will not function.  For example the IEEE1394 interface potentially in the P&amp;D connector will not have a connection point in the DVI interface and as such will not function.  Likewise, USB does not have a connection in the DVI connector.  Any interface with USB on the monitor side will have to use an alternative means of connecting USB to the system.

The DVI compliant system may have two T.M.D.S. links.  Any non-DVI compliant monitor that was based on T.M.D.S. electrical would not be able to take advantage of the bandwidth available from the second link.

To ensure the safety of the transmitter and to enable compatibility with a P&amp;D monitor, it is required that any adapter connecting a P&amp;D monitor to a DVI compliant system complies with requirements in section 2.2.9.

## 2.3. Bandwidth

## 2.3.1. Minimum Frequency Supported

The minimum frequency supported is specified to allow the link to differentiate between an active low-pixel format link and a power managed state (inactive link).  The lowest pixel format required by the DVI specification is 640x480@60 Hz (clock timing of 25.175 MHz). The DVI link can be considered inactive if the T. M. D.S. clock transitions at less than 22.5 MHz for more than one second.

## 2.3.2. Alternate Media

The T.M.D.S. transmission protocol is DC balanced and capable of being transmitted over fiber optic cable.  Specific details of a fiber optic implementation are not covered in this specification, but left to the designer.

Fiber optic implementations can be DVI compliant as long as the plug and play ability of the interconnect is still supported.  For example, the system must be able to read EDID data and detect a hot plug event.

For alternative media to be DVI compliant it is envisioned that the alternate media will serve as a connector to connector adapter.

## 2.4. Digital Monitor Power Management

The following digital monitor power management (hereinafter DMPM) definition is for power management as applied over the T.M.D.S. link for any monitor type.  Power management applied over the analog link is defined in section 2.5.4.  Six monitor power states are defined to provide programmatic control of monitor power and ensure the availability of the monitor identification data.  For completeness, the monitor power states include states entered via the power switch.

Monitor On Power State .  T.M.D.S. link is active.  Transmitter powered and active. Receiver powered and active.  This power state is equivalent to the DPMS "On" power state. EDID data is guaranteed to be available. DDC +5 volt signal is present, monitor drawing less than 10 mA current from DDC + 5 volt pin.

The monitor can leave this state if 1. The link becomes inactive as defined in 2.4.1, 2. The DDC +5 volt signal is removed, or 3. The monitor power switch is toggled.

Intermediate Power State .  T.M.D.S. link is inactive. Transmitter should be powered down. Receiver remains powered with receiver outputs optionally disabled.  The receiver must be able to detect the activation of the link and return the monitor to the "On" Power State.  A timer controls the duration of the Intermediate Power State.  This power state is similar to the DPMS "Suspend" power state allowing for the controller circuitry in the monitor to be powered as necessary to enable a quick recovery while dissipating less power than the "On" Power State.  EDID data is guaranteed to be available.  DDC +5 volt signal is present, monitor drawing less than 10 mA current from DDC + 5 volt pin.

The monitor can leave this state if 1. The link becomes active, 2. The DDC +5 volt signal is removed 3. The monitor power switch is toggled or 4. Monitor timer expires.

Active-Off Power State .  T.M.D.S. link is inactive.  Transmitter should be powered down. Receiver remains powered with receiver outputs optionally disabled.  The receiver must be able to detect the activation of the link and return the monitor to the "On" Power State.  This power state is equivalent to the DPMS "Off" state ("Active Off" in EDID 2.0 data structure). EDID data is guaranteed to be available.  DDC +5 volt signal is present, monitor drawing less than 50 mA current from DDC + 5 volt pin.

The monitor can leave this state if 1. The link becomes active, 2. The DDC +5 volt signal is removed, or 3. The monitor power switch is toggled

Non-Link Recoverable Off Power State . T.M.D.S. link is inactive.  Transmitter should be powered off.  Receiver should be powered off.  The Non-Link Recoverable Off Power State is entered when the DDC +5 volt signal has been removed from the monitor. EDID data is NOT

guaranteed to be available.  The "Non-Link Recoverable Off" Power State is not recoverable via activity on the T.M.D.S. link.  This power state is equivalent to the DPMS "Off (with No DPMS recovery)" power state identified in the EDID 2.0 data structure.

The monitor can leave this state if 1. The DDC +5 volt signal is reapplied or 2. The monitor power switch is toggled

Monitor Power Switch Off Power State .  This state is entered only when the power switch on the monitor is toggled to its off position.  This power state has two sub-states, with DDC +5 volt signal present and without DDC +5 volt signal present.  If the DDC +5 volt signal is present then EDID data is guaranteed to be available and the monitor must draw less than 50 mA current from the DDC +5 volt pin.  If the DDC +5 volt signal is not present then EDID data is NOT guaranteed to be available.

The monitor may toggle between the two sub states as appropriate depending on the state of the DDC +5 volt line.  The monitor may exit this power state only when the monitor power switch is toggled to the ON position.

## Power Management Architectural Note:

Table 2-2 is provided as a reference only to help clarify the relationship between the VESA DPMS specification and the DVI DMPM.

DMPM is similar to DPMS power management in that no requirement is placed on the power saving that must be achieved, and no requirement on the recovery time that must be met. These areas are left to the implementer to innovate.

The Intermediate Power State and the Active-Off power state can be combined by setting the timer value to zero.  The power switch state is simply for completeness and the Non-link recoverable Off power state is itself an innovation allowing monitors that wish to take advantage of this potentially substantial power savings state to do so.  Also the Non-Link Recoverable Off and the Monitor Power Switch Off power states can be combined by not putting a user-accessible power switch on the monitor.

The timer can be either hard wired at manufacture time, set to zero, or it could be programmable.

A dual input monitor could support only DPMS power management and as such would be in complete compliance with the DVI specification.  The caveat would be that you would never directly enter DPMS suspend (or stand-by) on the DVI interface.  Although DPMS does not list monitor power switch power states, these states still exist and must be correctly dealt with in a DPMS implementation.

Table 2-2. DPMS and DMPM comparison.

| DPMS STATE                                    | DPMS SPEC           | DVI - DMPM                   | DVI - DMPM   |
|-----------------------------------------------|---------------------|------------------------------|--------------|
| Monitor Power                                 | Mandatory           | Monitor Power on             | Mandatory    |
| Stand-By                                      | Optional            | Not Defined by DMPM          |              |
| Suspend                                       | Mandatory           | Intermediate Power State (1) | Optional     |
| Off                                           | Mandatory           | Active-Off                   | Mandatory    |
| Non-DPMS Recoverable Off (Listed in EDID 2.0) | Not Defined by DPMS | Non-Link Recoverable Off     | Optional     |
| Not Defined by DPMS                           | Not Defined by DPMS | Monitor Power Switch Off     | Optional     |

(1) The DMPM intermediate power state is a logical mapping to the DPMS suspend power state, not a direct mapping.

## 2.4.1. Link Inactivity Definition

An inactive T.M.D.S. link is defined as a link on which no logical transitions have occurred on the T.M.D.S. Data Enable (DE) for more than one second , or the T.M.D.S. clock line frequency falls below 22.5MHz for more than one second.

Note: It is acceptable for a monitor to consider a link inactive if the link is operating at an invalid frequency.  (I.e. one that is below the minimum required frequency as defined in section 2.3.1 Minimum Frequency Supported or a frequency not supported by the monitor).

## 2.4.2. System Power Management Requirements

A DVI compliant system must disable the T.M.D.S. link to transition the digital monitor into a low power mode.

## 2.4.3. Monitor Power Management Requirements

Two power states are required by any DVI compliant digital monitor: 1) Monitor On Power State, and 2) Active-Off Power State.  Additional power states may be optionally supported. Figure 2-2 is a monitor power state state-diagram.  A larger, printable version of Figure 2-2 in included in Appendix C for clarity.

If a monitor only supports the minimum requirement of two power states, then the monitor must only report active-off in the EDID data structure.

If a monitor supports the Intermediate Power State, then the monitor must indicate Suspend support in the EDID data structure.

If the monitor supports the Non-Link recoverable Off State, then the monitor must indicate Off with no DPMS recovery in the EDID data structure.

The monitor should enter a defined Power Management mode if the T.M.D.S. interface becomes inactive for greater than five seconds.

## 2.5. Analog

## 2.5.1. Analog Signal Quality

Systems implementing the analog portion of the DVI specification must be in compliance with the VSIS specification.  Refer to VESA VSIS Specification Version 1.6p for more information.

## 2.5.2. HSync and VSync Required

Both the system and the analog monitor are required to support separate HSync and VSync.

## 2.5.3. Analog Timings

Systems implementing the analog portion of the DVI specification should be in compliance with the VESA Industry Standards and Guidelines for Computer Display Monitor Timings specification, or the VESA Generalized Timing Formula Standard.

Note: It is anticipated that the monitor timer register will be defined in the EDID 1.3 data structure as an optionally writeable byte with 30-second resolution.  Zero seconds is an acceptable timer value.

Note: Transitions on the +5 volts signal take precedence over Link Active/Inactive and timer transitions

Figure 2-2. State Diagram, Monitor Power States

## 2.5.4. Analog Power Management

Systems implementing the analog portion of the DVI specification should be in compliance with the VESA DPMS Specification. Refer to VESA DPMS Specification Version 1.0 for more information.

## 2.6. Signal List

| Signal Name             | Signal Description                                                                                                           |
|-------------------------|------------------------------------------------------------------------------------------------------------------------------|
| T.M.D.S. Signals        |                                                                                                                              |
| T.M.D.S. Clock + &-     | T.M.D.S. clock differential pair                                                                                             |
| T.M.D.S. Clock Shield   | Shield for T.M.D.S. clock differential pair                                                                                  |
| T.M.D.S. Data0 + &-     | T.M.D.S. link #0 channel #0 differential pair                                                                                |
| T.M.D.S. Data0/5 Shield | Shared shield for T.M.D.S. link #0 channel #0 and link #1 channel #2                                                         |
| T.M.D.S. Data1 + &-     | T.M.D.S. link #0 channel #1 differential pair                                                                                |
| T.M.D.S. Data2/4 Shield | Shared shield for T.M.D.S. link #0 channel #2 and link #1 channel #1                                                         |
| T.M.D.S. Data2 + &-     | T.M.D.S. link #0 channel #2 differential pair                                                                                |
| T.M.D.S. Data1/3 Shield | Shared shield for T.M.D.S. link #0 channel #1 and link #1 channel #0                                                         |
| T.M.D.S. Data3 + &-     | T.M.D.S. link #1 channel #0 differential pair                                                                                |
| T.M.D.S. Data4 + &-     | T.M.D.S. link #1 channel #1 differential pair                                                                                |
| T.M.D.S. Data5 + &-     | T.M.D.S. link #1 channel #2 differential pair                                                                                |
| Control Signals         |                                                                                                                              |
| Hot Plug Detect (HPD)   | Signal is driven by monitor to enable the system to identify the presence of a monitor.                                      |
| DDC Data                | The data line for the DDC interface.                                                                                         |
| DDC Clock               | The clock line for the DDC interface.                                                                                        |
| +5V Power               | + 5 volt signal provided by the system to enable the monitor to provide EDID data when the monitor circuitry is not powered. |
| Ground (for +5V)        | Ground reference for +5 volt power pin. Used as return by HSync and VSync Signals                                            |
| Analog Signals          |                                                                                                                              |
| Analog Red              | Analog Red signal.                                                                                                           |
| Analog Green            | Analog Green signal.                                                                                                         |
| Analog Blue             | Analog Blue signal.                                                                                                          |
| Analog Horizontal Sync  | Horizontal synchronization signal for the analog interface.                                                                  |
| Analog Vertical Sync    | Vertical synchronization signal for the analog interface.                                                                    |
| Analog Ground           | Common ground for analog signals. Used as a return for analog red, green and blue signals only.                              |

## 3. T.M.D.S. Protocol Specification

## 3.1 Overview

## 3.1.1 Link Architecture

A T.M.D.S. transmitter encodes and serially transmits an input data stream over a T.M.D.S. link to a T.M.D.S. receiver (Figure 3-1). The T.M.D.S. encoding specification defines encoder and decoder functional requirements for transmission of the T.M.D.S. input stream over the link. Although the input stream to each link is represented as 24-bits wide within this specification, this is not intended to limit in any way the interface formats to the T.M.D.S. transmitter or receiver components. Transmitters and receivers are not required to present a 24-bit parallel interface to be compliant with this specification. The functionality of additional input and output layers also is not specified.

Figure 3-1. T.M.D.S. Link Architecture

The input stream contains pixel and control data. The transmitter encodes either pixel data or control data on any given input clock cycle, depending on the state of the data enable signal (DE). The active data enable signal indicates that pixel data is to be transmitted. Note that control (pixel) data is ignored when pixel (control) data is being transmitted. At the T.M.D.S. receiver, the recovered pixel (control) data may transition only when DE is active (inactive).

The transmitter contains three identical encoders, each driving one serial T.M.D.S. data channel. The input to each encoder is two control signals and eight bits of pixel data. Depending on the state of DE, the encoder will produce 10-bit T.M.D.S. characters from either the two control signals or from the eight bits of pixel data. The output of each decoder is a continuous stream of serialized T.M.D.S. characters.

## 3.1.2 Clocking

The T.M.D.S. clock channel carries a character-rate frequency reference from which the receiver produces a bit-rate sample clock for the incoming serial streams. Due to the high pair-to-pair skew that must be tolerated, the phase of the derived sample clock must be adjusted individually for each data channel. The methods of clock generation for data recovery are implementation specific and beyond the scope of this document.

## 3.1.3 Synchronization

The T.M.D.S. receiver must determine the location of character boundaries in the serial data streams. Once character boundaries are established on all data channels, the receiver is defined to be synchronized to the serial streams, and may recover T.M.D.S. characters from the data channels for decode. The T.M.D.S. data stream provides periodic cues for decoder synchronization.

The T.M.D.S. characters selected to represent pixel data contain five or fewer transitions, while the T.M.D.S. characters selected to represent the control data contain seven or more transitions. The high-transition content of the characters transmitted during the blanking period form the basis for character boundary synchronization at the decoder. While these characters are not individually unique in the serial data stream, they are sufficiently alike that the decoder may uniquely detect the presence of a succession of them during transmitted blanking intervals. The exact algorithm for this detection is an implementation detail beyond the scope of this document, but minimum conditions for receiver synchronization are defined.

## 3.1.4 Encoding

The T.M.D.S. data channel is driven with a continuous stream of 10-bit T.M.D.S. characters. During the blanking period there are four distinct characters that are transmitted, which map directly to the four possible states of the two input control signals input to the encoder. During active data, when each 10-bit character contains eight bits of pixel data, the encoded characters provide an approximate DC balance as well as a reduction in the number of transitions in the data stream. The encode process for the active data period can be viewed in two stages. The first stage produces a transition-minimized nine-bit code word from the input eight bits. The second stage produces a 10-bit code word, the finished T.M.D.S. character, which will manage the overall DC balance of the transmitted stream of characters.

The nine-bit code word produced by the first stage of the encoder is made up of an eight-bit representation of the transitions found in the input eight bits, plus a one-bit flag to indicate which of two methods was used to describe the transitions. In both cases the least significant bit of the output matches the least significant bit of the input. With a starting value established, the remaining seven bits of the output word is derived from sequential exclusive OR (XOR) or exclusive NOR (XNOR) functions of each bit of the input with the previously derived bit. The choice between XOR and XNOR logic is made such that the encoded values contain the fewest possible transitions, and the ninth bit of the code word is used to indicate whether XOR or XNOR functions were used to derive the output code word. The decode of this nine-bit code word is simply a matter of applying either XOR or XNOR gates to the adjacent bits of the code, with the least significant bit passing from decoder input to decoder output unchanged.

The second stage of the encoder during active data periods on the interface performs an approximate DC balance on the transmitted stream by selectively inverting the eight data bits of the nine-bit code words produced by the first stage. A tenth bit is added to the code word, to indicate when the inversion has been made. The encoder determines when to invert the next T.M.D.S. character based on the running disparity between ones and zeros that it tracks in the transmitted stream, and the number of ones and zeros found in the current code word. If too many ones have been transmitted and the input contains more ones than zeros, the code word is inverted. This dynamic encoding decision at the transmitter is simply decoded at the receiver by the conditional inversion of the input code word based on the tenth bit of the T.M.D.S. character.

## 3.1.5 Dual-Link Architecture

The number of data channels in the T.M.D.S. link architecture was originally chosen based on the combination of bandwidth required for video data and the logical simplicity of using one data channel each for red, green and blue pixel data. The dual T.M.D.S. link identified by this

specification uses six data channels sharing a single clock channel to double the bandwidth of the interface. For this configuration, the first data link transmits odd pixels while the second data link transmits even pixels. The first pixel of each line is pixel number one, an odd pixel.

## 3.2 Encoder Specification

## 3.2.1 Channel Mapping

The single-link T.M.D.S. transmitter consists of three identical encoders to which the input stream signals are mapped (Figure 3-2). Two control signals and eight bits of pixel data are mapped to each encoder. A dual-link transmitter incorporates an additional three data channels (Figure 3-3). The dual link configuration transmits the odd pixels of each horizontal line on the first link and the even pixels of each line on the second link. The first pixel of each line is pixel number one, an odd pixel.

Figure 3-2. Single link T.M.D.S. Channel Map

The use of all control signals other than horizontal sync (HSync) and vertical sync (VSync) is reserved. The control signals CTL1, CTL2, and CTL3, must be held to logic low at the transmitter input. It is recommended that CTL0 be also held to logic low, however for legacy reasons, some transmitter chips may send a control signal over CTL0. If this signal is sent over the CTL0 line, the only condition placed on it is that the rising edges of this signal occur at either the even edges or the odd edges of the single pixel input clock, it must not switch back forth between even and odd while the link is active.

Figure 3-3 Dual Link T.M.D.S. Channel Map

## 3.2.2 Encode Algorithm

The T.M.D.S. encoding algorithm is specified by Figure 3-5 with the definitions of Table 3-1. The encoder produces four unique 10-bit characters during blanking and one of 460 unique 10-bit characters during active data. Use of all other 10-bit characters over the link is reserved and must not be generated by the encoder.

| D, C0, C1, DE   | The encoder input data set. D is eight-bit pixel data, C1 and C0 are the control data for the channel, and DE is data enable                                                                                                                                                                                                                                                                                                                   |
|-----------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| cnt             | This is a register used to keep track of the data stream disparity. A positive value represents the excess number of '1's that have been transmitted. A negative value represents the excess number of '0's that have been transmitted. The expression cnt{t-1} indicates the previous value of the disparity for the previous set of input data. The expression cnt(t) indicates the new disparity setting for the current set of input data. |
| q_out           | These 10 bits are the encoded output value.                                                                                                                                                                                                                                                                                                                                                                                                    |
| N 1 {x}         | This operator returns the number of '1's in argument 'x'                                                                                                                                                                                                                                                                                                                                                                                       |
| N 0 {x}         | This operator returns the number of '0's in argument 'x'                                                                                                                                                                                                                                                                                                                                                                                       |

Table 3-1 Encoding Algorithm Definitions

Figure 3-5. T.M.D.S. Encode Algorithm

## 3.2.3 Serialization

The stream of T.M.D.S. characters produced by the encoder is serialized for transmission on the T.M.D.S. data channel. The least significant bit of each character (q\_out[0]) is the first bit to be transmitted.

## 3.3 Decoder Specification

## 3.3.1 Clock Recovery

A T.M.D.S. receiver must be capable of phase lock with a transmit clock from 25 MHz up to the stated maximum frequency of the receiver. Phase lock to the input clock must occur within 100 ms from the time that the input clock meets the electrical specifications of chapter four.

## 3.3.2 Data Synchronization

The receiver is required to establish synchronization with the data streams during any blanking period greater than 128 characters in length.

Prior to synchronization detection, and during periods of lost synchronization, the receiver shall not update the signals of the recovered stream.

## 3.3.3 Decode Algorithm

The T.M.D.S. decode algorithm is specified by Figure 3-6.

Figure 3-6 T.M.D.S. Decode Algorithm

## 3.3.4 Channel Mapping

The T.M.D.S. receiver aligns the data channel streams to a common clock and outputs the recovered T.M.D.S. stream as shown in Figure 3-2 and Figure 3-3.

## 3.3.5 Error Handling

There is no requirement for error handling over the T.M.D.S. link.

## 3.4 Link Timing Requirements

The maximum time for encode and serialization and decode is specified in order to bound latency across the interface. Figure 3-7 with Table 3-2 specifies these parameters.

Figure 3-7 T.M.D.S. Link Timing

| Symbol   | Description                                                                                                                                                                      |   Value | Unit    |
|----------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------|---------|
| t B      | Minimum duration blanking period required to ensure character boundary recovery at the receiver. Blanking periods of this duration must occur at least once every 50 mS (20 Hz). |     128 | T pixel |
| t E      | Maximum encoding/serializer pipeline delay                                                                                                                                       |      64 | T pixel |
| t R      | Maximum recovery/de-serializer pipeline delay. Recovery timing includes inter-channel skew, and is measured from the earliest DE transition among the data channels.             |      64 | T pixel |

Table 3-2 T.M.D.S. Link Timing Parameters

## 4. T.M.D.S. Electrical Specification

Some timing parameter values in this specification are based on the clock rate of the link while others are based on absolute values. For scalable timing parameters based on the clock rate, the time period of the clock is denoted as pixel time, or Tpixel . One tenth of the 'pixel time' is called the bit time, or Tbit . The bit time is also referred to as one Unit Interval , or UI, in the jitter and eye diagram specifications.

Schematic diagrams contained in this chapter are for illustration only and do not represent the only feasible implementation.

## 4.1. Overview

The conceptual schematic of one T.M.D.S. differential pair is shown in Figure 4-1. T.M.D.S. technology uses current drive to develop the low voltage differential signal at the receiver side of the DC-coupled transmission line. The link reference voltage AV cc sets the high voltage level of the differential signal, while the low voltage level is determined by the current source of the transmitter and the termination resistance at the receiver. The termination resistance (R T ) and the characteristic impedance of the cable (Z 0 ) must be matched.

Figure 4-1 Conceptual Schematic for one T.M.D.S. differential pair

A single-ended differential signal, representing either the positive or negative terminal of a differential pair, is illustrated in Figure 4-2. The nominal high-level voltage of the signal is AV cc and the nominal low-level voltage of the signal is (AV cc - V swing ). Since the swing is differential on the pair, the net signal on the pair has a swing twice that of the single-ended signal, or 2*V swing . The differential signal, as shown in Figure 4-3, swings between positive V swing and negative V swing .

Figure 4-2 Single-ended Differential Signal

Figure 4-3 Differential Signal

The signal test points for a T.M.D.S. link are shown in Figure 4-4. The first test point (TP1), at the pins of the T.M.D.S. transmitter, is not utilized for testing under this specification. Rather, the transmitter is tested at TP2, which includes the network from the transmitter to the connector as well as the connector to the cable assembly. The input to the receiver is similarly described by signal testing at TP3 rather than at TP4, the pins of the receiver. By imposing the signal quality requirements of these networks on transmitter and receiver components, link testing is reduced to measurements at only two test points. Cable assembly requirements are given by the allowable signal degradation between test points TP2 and TP3.

...

Figure 4-4 T.M.D.S. Link Test Points

The test procedures required to determine compliance with the specifications contained in sections 4.3, 4.4, 4.6, and 4.6 are described in section 4.7.

## 4.2. System Ratings and Operating Conditions

The maximum ratings of the T.M.D.S. interface are specified in Table 4-1. Exceeding these limits may damage the system.

Table 4-1 Maximum Ratings

| Item                                         | Value                         |
|----------------------------------------------|-------------------------------|
| Termination Supply Voltage, AV cc            | 4.0V                          |
| Signal Voltage on Any Signal Wire            | -0.5 to 4.0V                  |
| Common Mode Signal Voltage on Any Pair       | -0.5 to 4.0V                  |
| Differential Mode Signal Voltage on Any Pair | - 3.3V                        |
| Termination Resistance                       | 0 Ohms to Open Circuit        |
| Storage Temperature Range                    | -40 to 150 degrees Centigrade |

The required operating conditions of the T.M.D.S. interface are specified in Table 4-2.

Table 4-2 Required Operating Conditions

| Item                              | Value                      |
|-----------------------------------|----------------------------|
| Termination Supply Voltage, AV cc | 3.3V, - 5%                 |
| Termination Resistance            | 50 Ohms, - 10%             |
| Operating Temperature Range       | 0 to 70 degrees Centigrade |

## 4.3. Transmitter Electrical Specifications

The DVI interface requires a DC-coupled T.M.D.S. link. Transmitter electrical testing shall be performed using the test load shown in Figure 4-5.

Figure 4-5 Balanced Transmitter Test Load

The transmitter shall meet the DC specifications in Table 4-3 for all operating conditions specified in Table 4-2 when driving clock and data signals. The Vswing parameter identifies the minimum and maximum single-ended peak-to-peak signal amplitude that may be delivered by the transmitter into the test load).

## Item

## Value

Table 4-3 Transmitter DC Characteristics at TP2

| Single-ended high level output voltage, V H      | AV cc - 10mV                            |
|--------------------------------------------------|-----------------------------------------|
| Single-ended low level output voltage, V L       | (AV cc - 600mV) £ V L £ (AV cc - 400mV) |
| Single-ended output swing voltage, V swing       | 400mV £ V swing £ 600mV                 |
| Single-ended standby (off) output voltage, V OFF | AV cc - 10mV                            |

The transmitter shall meet the AC specifications in Table 4-4 across all operating conditions specified in Table 4-2. Rise and fall times are defined as the signal transition time between 20% and 80% of the nominal swing voltage (Vswing) of the device under test.

The transmitter intra-pair skew is the maximum allowable time difference (on both low-to-high and highto-low transitions) as measured at TP2, between the true and complement signals. This time difference is measured at the midpoint on the single-ended signal swing of the true and complement signals. The transmitter inter-pair skew is the maximum allowable time difference (on both low-to-high and high-to-low transitions) as measured at TP2, between any two single-ended data signals that do not constitute a differential pair.

Table 4-4 Transmitter AC Characteristics at TP2

| Item                                          | Value                                |
|-----------------------------------------------|--------------------------------------|
| Risetime/Falltime (20%-80%)                   | 75ps £ Risetime/Falltime £ 0.4 T bit |
| Intra-Pair Skew at Transmitter Connector, max | 0.15 T bit                           |
| Inter-Pair Skew at Transmitter Connector, max | 0.20 T pixel                         |
| Clock Jitter, max                             | 0.25 T bit                           |

For all channels under all operating conditions specified in Table 4-2, the transmitter shall have output levels at TP2, when terminated as shown in Figure 4-5, which meet the normalized eye diagram requirements of Figure 4-6. This requirement, normalized in both time and amplitude, specifies the minimum eye opening as well as the maximum overshoot and undershoot relative to the average differential swing voltage of the component under test. The time axis is normalized to the bit time at the testing frequency, while the amplitude axis is normalized to the average differential swing voltage. The average differential swing voltage is defined as the difference between the average differential amplitude when driving a logic one and the average differential amplitude when driving a logic zero. The average logic one appears at positive 0.5 on the vertical axis, while the average logic zero appears at negative 0.5. The normalized amplitude limits in Figure 4-6 allow 15% (of the average differential swing voltage) maximum overshoot and 25% maximum undershoot, relative to the amplitudes determined to be logic one and zero.

Normalized Time

Figure 4-6 Normalized Eye Diagram Mask at TP2

Combining the single-ended swing voltage (Vswing) specified in Table 4-3 with the overshoot and undershoot requirements of Figure 4-6, it is possible to calculate the minimum and maximum high-level voltage (Vhigh ) and low-level voltage (Vlow) that is allowable on the interface.

<!-- formula-not-decoded -->

Vhigh (min) = Vswing (min) - 25% * (2*Vswing  (min) ) = 400 - 200 = 200 mV

Vlow (max) = -Vswing (max) - 15% * (2*Vswing  (max) ) = -600 - 180 = -780 mV

Vlow (min) = -Vswing (min) + 25% * (2*Vswing  (min) ) = -400 + 200 = -200 mV

Minimum opening at transmitter = Vhigh (min) - Vlow (min) = 400 mV

Transmitter eye diagram test procedures are defined in section 4.7.6. The transmitter eye diagram mask of Figure 4-6 is not used for response time and clock jitter specifications, but specifies the clock to data jitter indirectly.

## 4.4. Receiver Electrical Specifications

The receiver shall meet the signal requirements listed in Table 4-5, Table 4-6, and Table 4-7 for all operating conditions specified in Table 4-2.

| Item                                               | Value                                |
|----------------------------------------------------|--------------------------------------|
| Differential Input Voltage, V idiff                | 150 £ V idiff £ 1200 mV              |
| Input Common Mode Voltage, V icm                   | (AV cc - 300) £ V icm £ (AV cc - 37) |
| Behavior when Transmitter Disabled or Disconnected | AV cc - 10 mV                        |

Table 4-5 Receiver DC Characteristics at TP3

Table 4-6 Receiver AC Characteristics at TP3

| Item                                            | Value       |
|-------------------------------------------------|-------------|
| Minimum differential sensitivity (peak-to-peak) | 150 mV      |
| Maximum differential input (peak-to-peak)       | 1560 mV     |
| Allowable Intra-Pair Skew at Receiver Connector | 0.4 T bit   |
| Allowable Inter-Pair Skew at Receiver Connector | 0.6 T pixel |

Table 4-7 Receiver Impedance Characteristics at TP3

| Item                 | Value      |
|----------------------|------------|
| TDR Rise Time        | 75 ps      |
| Exception_window a   | 500 ps     |
| Through_connection b | 100 - 20 W |
| At Termination c     | 100 - 10 W |

a Within the Exception\_window no single impedance excursion shall exceed the Through\_connection impedance tolerance for a period of twice the TDR rise time specification. The maximum excursion within the Exception\_window at TP3 shall not exceed +75% and -25% of the nominal cable impedance.

b Through\_connection impedance describes the impedance tolerance through a mated connector. This tolerance is greater than the termination or cable impedance due to limits in the technology of the connectors.

c The input impedance at TP3, for the termination, shall be recorded 4.0 ns following the reference location determined by an open connector between TP3 and TP4.

For all channels under all operating conditions specified in Table 4-2, the receiver shall reproduce a test data stream, with pixel error rate 10 -9 , when presented with input amplitude illustrated by the eye diagram of Figure 4-7.

Normalized Time

Figure 4-7 Absolute Eye Diagram Mask at TP3

## 4.5. Cable Assembly Specifications

When driven by an input waveform meeting the eye diagram mask requirements of Figure 4-6 a DVI cable assembly must a produce an output waveform that meets the receiver eye diagram mask of Figure 4-7. In addition, the cable assembly must meet the signal skew requirements of Table 4-8.

Table 4-8 Cable Assembly Skew Budget (informative)

| Item                                   | Value       |
|----------------------------------------|-------------|
| Maximum Cable Assembly Intra-Pair Skew | 0.25 T bit  |
| Maximum Cable Assembly Inter-Pair Skew | 0.4 T pixel |

## 4.6. Jitter Specifications

The differential clock of the T.M.D.S. link shall meet the total jitter specifications defined in Table 4-9. The clock to data jitter is not specified in the table but the system shall produce the eye diagram shown in Figure 4-7 when measured at test point TP3. Normative values are highlighted in bold . All other values are informative. Compliance test points are defined in Figure 4-4. The Unit Interval (UI) is equal to one bit time (Tbit ).

Table 4-9 T.M.D.S. Clock Jitter Budget

| Compliance Test Point   | Total Jitter [UI]   |
|-------------------------|---------------------|
| TP2                     | 0.25                |
| TP2 to TP3              | 0. 165 a            |
| TP3                     | 0.30                |

a The total jitter from TP2 to TP3 is calculated based on the assumption that the distribution of the jitter is Gaussian.

## 4.7. Electrical Measurement Procedures

Electrical measurements shall be performed as described in this clause.

## 4.7.1. Test Patterns

Two different test patterns are used to evaluate T.M.D.S. interface components. For pixel error rate measurements, a (2 23 -1) bit pseudo-random data pattern is transmitted. Other measurements specify a 'half clock' sequence. The half clock pattern consists of alternating 0x3FF (all ones) and 0x000 (all zeros) T.M.D.S. characters. This pattern is useful for determining average swing voltage, logic one, and logic zero voltage levels.

## 4.7.2. Normalized Amplitudes

Normalized amplitude measurements are necessary for both single-ended and differential testing of the T.M.D.S. interface. These measurements are made with transmission of the half clock test pattern, and the time base of the measurement equipment set to a scale that is coarse enough to observe at least two full pixel times. The average high-level and low-level amplitudes are determined at the point where signal ringing has subsided. These averages establish the swing voltage and are used to normalize the eye diagram.

## 4.7.3. Clock Recovery

Eye diagram measurements require a clock which has been recovered from the transmit stream. The clock recovery unit is used to remove low frequency jitter from the measurement as shown in Figure 4-8. The clock recovery unit has a low pass filter with 20dB/decade rolloff with -3dB point of 4 MHz. It is used to approximate the phase locked loop in the receiver. The receiver is able to track a large amount of low frequency jitter (such as drift or wander) below this bandwidth. This low frequency jitter would create a large measurement penalty, but does not affect the operation of the link.

Figure 4-8 Clock Recovery Unit in Eye Diagram Measurements

The eye diagrams produced with by this method will contain only high frequency jitter components that are not tracked by the clock recovery circuit of the receiver. The clock recovery unit may be a T.M.D.S. receiver meeting the filter requirements above.

## 4.7.4. Transmitter Rise/Fall Time

Rise time is a differential measurement across the outputs of a differential pair with a load present (including test equipment) equivalent to that shown in Figure 4-5. Both rising and falling edges are measured. The 100% and 0% levels are the normalized 1 and 0 levels present when sending half clock characters (4.7.1).

Once the normalized amplitude is determined, the time base is changed to a finer scale to measure the rise and fall time. The half clock data pattern (4.7.1) is transmitted for the rise and fall time measurements. The rise time specification is the time interval between the normalized 20% and 80% amplitude levels. It is recommended to utilize the averaging feature of the equipment to read more stable values.

When the equipment's rise time is not negligible compared to the signal's rise time, the effect of the equipment should be removed using the equation:

<!-- formula-not-decoded -->

In order to keep the measurement error under 10% when using this equation, it is necessary that the equipment rise time be less than one third of the signal rise time.

## 4.7.5. Transmitter Skew Measurement

The transmitter skew is the time difference between the two differential signals measured at the normalized 50% crossover point with a load present (including test equipment) equivalent to that shown in Figure 4-5. This measurement is taken using two single ended probes. Skew in the test set-up must be calibrated and removed from the recorded measurements. All of the signal pairs must be measured and the worst case recorded.

Normalized amplitudes are determined using the method described in 4.7.2.

The device under test transmits a continuous half clock character pattern as defined in 4.7.1. The data is averaged using an averaging scope. An easy method to view and measure the skew between these signals is to invert one of the signals.

## 4.7.6. Transmitter Eye

This test is made as a differential measurement at TP2 of 100,000 acquisitions to achieve 99% confidence within 1% error of the mean value assuming normal distribution of the waveforms in the eye diagram. Referring to Figure 4-6, there are eight critical locations to collect the data of the means and standard deviations: at six horizontal segments of (0 &lt; x &lt; 0.15, y=0), (0.85 &lt; x &lt; 1.0, y=0), (0 &lt; x &lt; 0.32, y=0.25), (0.68 &lt; x &lt; 1.0, y=0.25), (0 &lt; x &lt;0.32, y=-0.25), (0.68 &lt; x &lt; 1.0, y=-0.25), and at two vertical segments of (x=0.5, 0.25 &lt; y &lt; 0.65) and (x=0.5, -0.65 &lt; y &lt; -0.25).

The mean and standard deviation at each of the eight critical regions around the eye are used for time statistics at the six horizontal locations and for amplitude statistics at the two vertical locations. In all cases the eye must be degraded by -6 sigma limit points for the pixel error rate of 10 -9 .

The scope trigger must be a recovered clock as defined in 4.7.3. The data pattern for this test is the pseudorandom data pattern defined in 4.7.1.

## 4.7.7. Jitter Measurement

Jitter measurement is performed as a differential measurement of the rising edge of the clock signal (clk+ minus clk-) at TP2 and TP3. The scope trigger must be a recovered clock as defined in 4.7.3. The scope is used to determine the standard deviation of the 50% crossings in measuring time statistics of the differential clock signal. The random jitter at 10 -9 pixel error rate will be -6 sigma limit points of the distribution. When the jitter includes any systematic components, care must be taken in obtaining the sigma value from the scope, otherwise the overestimated sigma value can lead to an excessively large value of the jitter limit.

## 4.7.8. Receiver Eye

This differential measurement is made at TP3, through mated connectors with a load present (including test equipment) equivalent to that shown in Figure 4-5.

This test is made as a differential measurement at TP2 of 100,000 acquisitions to achieve 99% confidence within 1% error of the mean value assuming normal distribution of the waveforms in the eye diagram. Referring to Figure 4-7, there are eight critical locations to collect the data of the means and standard deviations: at six horizontal segments of (0 &lt; x &lt; 0.25, y=0), (0.75 &lt; x &lt; 1.0, y=0), (0 &lt; x &lt; 0.30, y=75mv), (0.70 &lt; x &lt; 1.0, y=75mv), (0 &lt; x &lt;0.30, y=-75mv), (0.70 &lt; x &lt; 1.0, y=-75mv), and at two vertical segments of (x=0.5, 75mv &lt; y &lt; 780mv) and (x=0.5, -780mv &lt; y &lt; -75mv).

The mean and standard deviation at each of the eight critical regions around the eye are used for time statistics at the six horizontal locations and for amplitude statistics at the two vertical locations. In all cases the eye must be degraded by -6 sigma limit points for the pixel error rate of 10 -9 .

The scope trigger must be a recovered clock as in 4.7.3 and the transmitted data pattern is pseudo-random as defined in 4.7.1.

## 4.7.9. Receiver Skew Measurement

This single ended measurement is made at TP3, through mated connectors with a load present (including test equipment) equivalent to that shown in Figure 4-5.

The same method is used as for transmitter skew in 4.7.5.

## 4.7.10. Differential TDR Measurement Procedure

The differential time-domain reflectometry (TDR) test setup measures the reflected waveform returned from a load when driven with a step input. It is obtained by driving the load under test with a step waveform using a driver with a specified source impedance and rise time. The reflected waveform is the difference between (a) the observed waveform at the device under test when driven with the specified test signal, and (b) the waveform that results when driving a standard test load with the same specified test signal. From this measurement result we can infer the impedance of the device under test.

The driving waveform is sourced from a balanced, differential 100-ohm source with a 75 ps rise time.

## 5. Physical Interconnect Specification

## 5.1. Overview

DVI complaint host systems may provide either a digital only interface or a combined analog and digital interface. The system-side connector distinguishes the system capabilities. The two defined connectors have the same physical outer dimensions. In each case the digital signals are present, allowing a monitor with a digital interface to attach directly to either system connector. Because the digital only receptacle does not have sockets for the analog pins of an analog monitor, the plug of an analog monitor will not mate with the digital only system.

## 5.2. Mechanical Characteristics

## 5.2.1. Signal Pin Assignments

## 5.2.1.1. Digital-Only Connector

The digital only connector contains 24 signal contacts organized in three rows of eight contacts. Signal pin assignments are listed in Table 5-1.

|   Pin | Signal Assignment       |   Pin | Signal Assignment       |   Pin | Signal Assignment       |
|-------|-------------------------|-------|-------------------------|-------|-------------------------|
|     1 | T.M.D.S. Data2-         |     9 | T.M.D.S. Data1-         |    17 | T.M.D.S. Data0-         |
|     2 | T.M.D.S. Data2+         |    10 | T.M.D.S. Data1+         |    18 | T.M.D.S. Data0+         |
|     3 | T.M.D.S. Data2/4 Shield |    11 | T.M.D.S. Data1/3 Shield |    19 | T.M.D.S. Data0/5 Shield |
|     4 | T.M.D.S. Data4-         |    12 | T.M.D.S. Data3-         |    20 | T.M.D.S. Data5-         |
|     5 | T.M.D.S. Data4+         |    13 | T.M.D.S. Data3+         |    21 | T.M.D.S. Data5+         |
|     6 | DDC Clock               |    14 | +5V Power               |    22 | T.M.D.S. Clock Shield   |
|     7 | DDC Data                |    15 | Ground (for +5V)        |    23 | T.M.D.S. Clock+         |
|     8 | No Connect              |    16 | Hot Plug Detect         |    24 | T.M.D.S. Clock-         |

Table 5-1 Digital-Only Connector Pin Assignments

## 5.2.1.2. Combined Connector

The mechanical interconnect includes 29 signal contacts, which are divided into two sections. The first section is organized as three rows of eight contacts. The second section contains five signals that are designed specifically for analog video signals. Horizontal sync, Vertical sync, R, G, and B are all are required for analog implementations. Signal pin assignments are listed in Table 5-2.

Table 5-2 Combined Analog and Digital Connector Pin Assignments

| Pin   | Signal Assignment       | Pin   | Signal Assignment                         | Pin   | Signal Assignment       |
|-------|-------------------------|-------|-------------------------------------------|-------|-------------------------|
| 1     | T.M.D.S. Data2-         | 9     | T.M.D.S. Data1-                           | 17    | T.M.D.S. Data0-         |
| 2     | T.M.D.S. Data2+         | 10    | T.M.D.S. Data1+                           | 18    | T.M.D.S. Data0+         |
| 3     | T.M.D.S. Data2/4 Shield | 11    | T.M.D.S. Data1/3 Shield                   | 19    | T.M.D.S. Data0/5 Shield |
| 4     | T.M.D.S. Data4-         | 12    | T.M.D.S. Data3-                           | 20    | T.M.D.S. Data5-         |
| 5     | T.M.D.S. Data4+         | 13    | T.M.D.S. Data3+                           | 21    | T.M.D.S. Data5+         |
| 6     | DDC Clock               | 14    | +5V Power                                 | 22    | T.M.D.S. Clock Shield   |
| 7     | DDC Data                | 15    | Ground (return for +5V, HSync, and VSync) | 23    | T.M.D.S. Clock+         |
| 8     | Analog Vertical Sync    | 16    | Hot Plug Detect                           | 24    | T.M.D.S. Clock-         |
| C1    | Analog Red              | C2    | Analog Green                              | C3    | Analog Blue             |
| C4    | Analog Horizontal Sync  | C5    | Analog Ground (analog R, G, &Breturn)     |       |                         |

## 5.2.2. Contact Sequence

| Connection   | Signal Pins                                                      |
|--------------|------------------------------------------------------------------|
| First Make   | Connector shell                                                  |
| Second Make  | C5 (analog ground, when present)                                 |
| Third Make   | Pins 1 through 13 and 15 through 24                              |
| Fourth Make  | C1, C2, C3, C4 (analog signals, when present) Pin 14 (+5V power) |

Table 5-3 Mating Contact Sequence

## 5.2.3. Digital-Only Receptacle Connectors

## 5.2.3.1. Mating Interface Dimensions

Figure 5-1 Digital-only Receptacle Connector Mating Interface Dimensions

## 5.2.3.2. Recommended Printed Circuit Board Hole Pattern and Keep Out

Figure 5-2 Recommended Digital-only Receptacle Connector PCB Layout

## 5.2.4. Combined Analog and Digital Receptacle Connectors

## 5.2.4.1. Mating Interface Dimensions

Figure 5-3 Combined Receptacle Connector Mating Interface Dimensions

## 5.2.4.2. Recommended Printed Circuit Board Hole Pattern and Keep Out

Figure 5-4 Recommended Combined Receptacle Connector PCB Layout

## 5.2.5. Digital Plug Connectors

## 5.2.5.1. Mating Interface Dimensions

Figure 5-5 Digital Plug Connector Mating Interface Dimensions

## 5.2.6. Analog Plug Connectors

## 5.2.6.1. Mating Interface Dimensions

Figure 5-6 Analog Plug Connector Mating Interface Dimensions

## 5.2.7. Recommended Panel Cutout

Figure 5-7 Recommended Panel Cutout for Receptacle Connectors

## 5.2.8. Mechanical Performance

This section summarizes the mechanical performance requirements for the DVI connector interface. Where appropriate the relevant ANSI/EIA-364 Test Procedures and Conditions are referenced. Please refer to section 5.5 for detailed test sequence flow charts.

| Item                    | Test Condition                                                                              | Requirement                                                                                                                                                                                                                                                          |
|-------------------------|---------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Vibration               | ANSI/EIA-364-28, Condition III Method 5A, 15 minute/axis                                    | No discontinuity at 1 m s or longer (each contact) when continuity is tested per ANSI/EIA-364-46                                                                                                                                                                     |
| Mechanical Shock        | ANSI/EIA-364-27 Condition A (specified pulse)                                               | No discontinuity at 1 m s or longer (each contact) when continuity is tested per ANSI/EIA-364-46                                                                                                                                                                     |
| Durability              | ANSI/EIA-364-09 Automatic cycling to 100 cycles Rate: 100 + 50 cycles per hour              | Low Level contact resistance per ANSI/EIA-364-23 10 m W maximum change from initial per contact pair All samples to be mated                                                                                                                                         |
| Mating &Unmating Forces | ANSI/EIA-364-13 Insert and extract at a speed of 25mm/minute                                | Unmating force: 1 kg force minimum, 4 kg force maximum Mating force: 4.5 kg force maximum                                                                                                                                                                            |
| Cable Flexing           | ANSI/EIA-364-41 Condition I Dimension X=3.7 x cable diameter 100 cycles in each of 2 planes | Dielectric Withstanding Voltage tested per requirements of section 5.3. Insulation Resistance tested per requirements of section 5.3 Continuity tested per ANSI/EIA-364- 46 with no discontinuities on contacts or shield greater than 1 m s allowed during flexing. |

## 5.3. Electrical Characteristics

## 5.3.1. Connector Electrical Performance

This section summarizes the electrical performance requirements for the DVI connector interface. Where appropriate the relevant ANSI/EIA-364 Test Procedures and Conditions are referenced. Please refer to section 5.5 for detailed test sequence flow charts.

| Item                            | Test Condition                                                                                                                                                   | Requirement                                                                                                   |
|---------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------|
| Contact Resistance              | ANSI/EIA-364-23                                                                                                                                                  | 20 m W , maximum, initial per contact mated pair 10 m W , maximum change from original per contact mated pair |
| Shell Resistance                | ANSI/EIA-364-06A-83 Contact resistance measured from receptacle shell leg to plug cable braid. Test current = 100mA; Test voltage = 5 V DC open circuit maximum. | 50 m W , maximum initial 50 m W , maximum change from original                                                |
| Dielectric Withstanding Voltage | ANSI/EIA-364-20 Test voltage 500 V DC + 50V Method C, unmated and unmounted Barometric pressure of 15 psi                                                        | No flashover, No sparkover, No excess leakage, No breakdown.                                                  |
| Insulation Resistance           | ANSI/EIA-364-21 Test voltage 500 V DC + 50 V Method C, unmated and unmounted                                                                                     | 1 G W minimum between adjacent contacts and contacts and shell.                                               |
| Contact Current Rating          | ANSI/EIA-364-70, TP-70 55 o C, maximum ambient 85 o C, maximum temperature change                                                                                | 1.5 A minimum                                                                                                 |
| Applied Voltage Rating          |                                                                                                                                                                  | 40 Volts AC (rms) continuous maximum, on any signal pin with respect to the shield                            |
| Electrostatic Discharge         | IEC 801-2 Test unmated from 1kV to 8kV in 1 kV steps using 8mm ball probe                                                                                        | No evidence of discharge to contacts. Discharge to the shell is acceptable.                                   |

| Item                                        | Test Condition                                                                                                                                                                                                                                                                                                          | Requirement                                                                    |
|---------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| T.M.D.S. Signal Time Domain Impedance       | ANSI/EIA-364-108 Draft Proposal Risetime = 330 pS (10%-90%) S:G ratio per DVI pin designation Differential Measurement Specimen Environment Impedance = 100 W differential Source-side receptacle connector mounted on a controlled impedance pcb fixture                                                               | 100 W- 15%                                                                     |
| T.M.D.S. Signal Time Domain Crosstalk: FEXT | ANSI/EIA-364-90 Draft Proposal Risetime = 330 pS (10%-90%) S:G ratio per DVI pin designation Differential Measurement Specimen Environment Impedance = 100 W differential Source-side receptacle and the load side plug connector are mounted on a controlled impedance pcb fixture (1) Driven pair and (1) victim pair | 5% Maximum                                                                     |
| T.M.D.S. Signal Rise Time Degradation       | ANSI/EIA-364-102 S:G ratio per DVI pin designation Differential Measurement Specimen Environment Impedance = 100 W differential Source-side receptacle and the load side plug connector mounted are on a controlled impedance pcb fixture                                                                               | 160 pS Maximum (Note: Converted bandwidth using BW=0.35/t rise yields 2.2 GHz) |

| Item                                                  | Test Condition                                                                                                                                                                                                                                                                                                                                                    | Requirement                                                                    |
|-------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| Analog RGB Coaxial Signal Time Domain Impedance       | ANSI/EIA-364-108 Draft Proposal Risetime = 700 pS (10%-90%) S:G ratio per DVI pin designation Single-ended Measurement Specimen Environment Impedance = 75 W single-ended Source-side receptacle connector mounted on a controlled impedance pcb fixture                                                                                                          | 75 W - 10%                                                                     |
| Analog RGB Coaxial Signal Time Domain Crosstalk: FEXT | ANSI/EIA-364-90 Draft Proposal Risetime = 700 pS (10%-90%) S:G ratio per DVI pin designation Single-ended Measurement Specimen Environment Impedance = 75 W single-ended Source-side receptacle connector is mounted on a controlled impedance pcb fixture and the load side plug connector is terminated to semi-rigid coax. (1) Driven line and (1) victim line | 3% Maximum                                                                     |
| Analog RGB Coaxial Signal Rise Time Degradation       | ANSI/EIA-364-102 S:G ratio per DVI pin designation Single-ended Measurement Specimen Environment Impedance = 75 W single-ended Source-side receptacle connector is mounted on a controlled impedance pcb fixture and the load side plug connector is terminated to semi-rigid coax.                                                                               | 140 pS Maximum (Note: Converted bandwidth using BW=0.35/t rise yields 2.5 GHz) |

## 5.3.2. Cable Electrical Performance

This section summarizes the electrical performance requirements for coaxial cable used in the DVI cable assembly.

| Item                                      | Test Condition                               | Requirement                                                                                                               |
|-------------------------------------------|----------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| Analog RGB Signal Conductor Impedance     |                                              | 75 W - 4 W                                                                                                                |
| Analog RGB Signal Conductor DC Resistance | At 20 C                                      | 1.8 W Maximum                                                                                                             |
| Analog RGB Signal Attenuation             | Frequency (MHz) 1 10 50 100 200 400 700 1000 | 0.14 dB Maximum 0.45 dB Maximum 1.0 dB Maximum 1.5 dB Maximum 2.1 dB Maximum 3.0 dB Maximum 4.3 dB Maximum 5.4 dB Maximum |

## 5.4. Environmental Characteristics

This section summarizes the environmental performance requirements for the DVI connector interface. Where appropriate the relevant ANSI/EIA-364 Test Procedures and Conditions are referenced. Please refer to section 5.5 for detailed test sequence flow charts.

| Item               | Test Condition                                                    | Requirement                                                                                                                  |
|--------------------|-------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|
| Thermal Shock      | ANSI EIA-364-32, Condition 1 10 cycles, mated                     | Low Level contact resistance per ANSI/EIA-364-23 10 m W maximum change from initial per contact pair All samples to be mated |
| Cyclic Humidity    | ANSI/EIA-364-31, conditionsA andB Method III, omit 7A and 7B      | Low Level contact resistance per ANSI/EIA-364-23 10 m W maximum change from initial per contact pair All samples to be mated |
| Temperature Life   | ANSI/EIA-364-17 Condition 4 105 o C for 250 hours Method A, mated | Low Level contact resistance per ANSI/EIA-364-23 10 m W maximum change from initial per contact pair All samples to be mated |
| Temperature Rating | Operating                                                         | -20 C to +85 C                                                                                                               |
| Temperature Rating | Non-Operating                                                     | -20 C to +85 C                                                                                                               |

## 5.5. Test Sequences

## 5.5.1. Group 1: Mated Environmental

## Number of Samples:

- (5) Receptacles assembled to printed circuit board
- (5) Cable assemblies with a plug assembled to one end, 25.4 cm long

## 5.5.2. Group II: Mated Mechanical

## Number of Samples:

- (2) Receptacles, assembled to printed circuit board
- (2) Cable assemblies with a plug assembled to one end, 25.4 cm long

Note: Connector is to be mounted on a fixture that simulates the typical application. The receptacle connector shall be mounted to a panel, per the receptacle panel cutout in shown in Figure 5-7, which is permanently affixed to the fixture. The plug shall be mated to the receptacle with jackscrews fully engaged and the other end of the cable shall be permanently clamped to the fixture.

## 5.5.3. Group III: Mechanical Mate/Unmate Forces

## Number of Samples:

- (2) Receptacles, assembled to printed circuit board
- (2) Cable assemblies with a plug assembled to one end, 25.4 cm long

## 5.5.4. Group IV: Insulator Integrity

## Number of Samples:

- (2) Receptacles, assembled to printed circuit board
- (2) Cable assemblies with a plug assembled to one end, 25.4 cm long

## 5.5.5. Group V: Cable Flexing

## Number of Samples:

- (2) Cable assemblies

## 5.5.6. Group VI: Electrostatic Discharge

(/(&amp;75267$7,&amp; ',6&amp;+$5*(

## Number of Samples:

- (1) Receptacle connector

## Appendix A.

## Glossary of Terms

## Active Data Period

Time on the T.M.D.S. link during which DE is active and pixel data encodings are present on the link.

## Blanking Period

Time on the T.M.D.S. link during which DE is inactive and control signal encodings are present on the link.

## Channel

A T.M.D.S. channel is a single differential signaling pair.

## Control Signals

Additional signals to be transported over the T.M.D.S. link.

## Data Enable

A link-control signal indicating whether pixel data or control signals are to be transmitted.

## Dual T.M.D.S. Link

Six T.M.D.S. data channels plus one T.M.D.S. clock channel. The six data channels are referred to as channels 0 through 5. The clock channel is sometimes referred to as channel C.

## HSync

Horizontal synchronization signal typically used for CRT monitors.

## In-band characters

The collection of T.M.D.S. characters used to represent pixel data on the T.M.D.S. link.

## Link

A T.M.D.S. link is the entire three channels and clock pair required to transmit RGB data

## Out-of-band characters

The collection of T.M.D.S. characters used to represent control signals on the T.M.D.S. link.

## Pel

Pixel element.  A pel is a pixel element, i.e. the singular red value or green value or blue value of and RGB pixel.

## Pixel Data

24-bit data to be transported over the T.M.D.S. link. The three individual bytes of the pixel data, which are mapped onto individual T.M.D.S. data channels, are sometimes referred to as red, grn, and blu.

## Recovered Stream

A T.M.D.S. input stream recreated a T.M.D.S. receiver.

## T.M.D.S.

Transition minimized differential signal.

## T.M.D.S. characters

These are encoded 10-bit values which appear, serialized, on the T.M.D.S. data channels.

## T.M.D.S. Clock Channel

A signal carrying a frequency reference for T.M.D.S. data channels.

## T.M.D.S. Data Channel

A single serial stream of T.M.D.S. encoded data.

## T.M.D.S. Data Link

An infrequently used term to identify three T.M.D.S. data channels. A dual T.M.D.S. link might thus be referred to as two T.M.D.S. data links plus one T.M.D.S. clock channel.

## T.M.D.S. Input Stream

The collection of input signals to a T.M.D.S. transmitter for transmission over the T.M.D.S. link. This includes 24-bit pixel data, six control signals to be transmitted over the link, a linkcontrolling data enable signal, and a clock to which all input signals are synchronous.

## T.M.D.S. Link

Three T.M.D.S. data channels plus one T.M.D.S. clock channel. The three data channels are referred to as channel 0, channel 1, and channel 2. The clock channel is sometimes referred to as channel C.

## VESA, Video Electronics Standards Association

North First Street, Suite 440

San Jose, CA  95131-2029

## VSync

Vertical synchronization signal typically used for CRT monitors.

## Appendix B.       Contact Geometry

The following document, ES-74320-900 (sheets 1-14) contains the technical design details required for compliance to the DVI plug and receptacle connector system. The information provided is covered by U.S. Patents 4,470,180 and 5,102,353 and is to be used solely for the purpose of compliance to the DVI specification. It is governed by the DDWG license agreements and associated compliance documentation.

3DJH    RI

## Appendix C. Digital Monitor Power States

Note: Transitions on the +5 volts signal take precedence over Link Active/Inactive and timer transitions
